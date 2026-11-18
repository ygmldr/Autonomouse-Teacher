# Autonomous Teacher — M0 G4 PreLive 无 Key 准入工程：Agent 执行任务书 v1.0

> **任务类型**：可直接交接的 implementation + adversarial review plan，不是实际 Live 授权。
>
> **起点（2026-11-18）**：`ygmldr/Autonomouse-Teacher` 远程 `main=017c747631cae1e7788014c4ef9e6056c141fecd`；G3-D 冻结实现 `cf40c6bfb84ceae98e795db19efa955aa3035991`，独立复核 `PASS_FOR_G3D_NO_KEY_OS_BOUNDARY_SCOPE`；G3-D 最终矩阵 53/53 PASS。Agent 开始执行时必须重新读取实际 HEAD，发现漂移先记录，而不是强制 reset。
>
> **本轮唯一授权范围**：G4-A～G4-E 的 **无真实凭据、无真实 Provider、无外部网络** 工程准备、模拟验证、独立 Review。不得签发 G4 Full PASS；不得进入 G5/G6；不得解除任何 LiveGate；不得启动付款服务或真实 HTTP。
>
> **上层依据**：`docs/Autonomous_Teacher_M0_G2L11_to_G6_Agent_Playbook_2026-11-16.md` 第 10–12 节；`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md`；`docs/E5_PRELIVE_NO_KEY_REPORT.md`；`docs/REVIEW_G3D_INDEPENDENT.md`；`docs/M0_G3D_REVIEW_ERRATA.md`；`docs/SECURITY_APPROVALS.md`；`docs/THREAT_MODEL.md`；`AGENTS.md`。本文与以上文件不一致时，一律先记录冲突并提交 Lead，不能自行宽松化。

---

## 0. 给 Lead Agent 的执行指令（先读）

你是 Lead/编排者：按仓库 `AGENTS.md`，**仅协调、审计、验证，不直接改产品文件**；实际编码和证据采集委托不同 Implementation Agents；Independent Reviewer 不参与实现和写入被冻结的证据。原则是 **最小改动，复用 G3-D，不再重造 G2/G3**。

1. 先执行 G4-00 基线核对与三个维护者待决 P2（不必等用户交互即可先继续 **无 Key 工程**）。
2. 分派 G4-A 身份/批准门、G4-B 冻结输入/Registry、G4-C 模拟可信 Egress、G4-D Watchdog/Revocation/E5 离线验证；彼此按接口契约协作，**不得并发修改同一个文件**。
3. 集成后走 G4-E：冻结提交 → 负例重跑 → 交给未参与实现的 Reviewer → STOP。
4. **任何** agent 看到能让当前 `LiveGate` 返回 ALLOWED/GO、能注入真实 Key、能访问公共网络、能绕开 Broker Claim 的变更，立即中止、撤回该变更、保全证据并报告。
5. 交付允许的最高裁定为 `PASS_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE`；**`E5_PRELIVE_FULL` 必须保持 `BLOCKED_PENDING_HUMAN_DEPLOYMENT`**。报告状态只能以测试真实运行结果填写。

### 0.1 当前已知事实（勿重做历史）

- G3-D：双 OS principal、受限 UDS `0660`/GID 2000、`SO_PEERCRED`、候选无可信状态挂载、真实 DSH 0.2.2-rc.2 的 Echo/Tool/Resume 和崩溃复核已通过；Reviewer P0=0、P1=0，但 PASS 仅限 **本机冻结 SHA、0 Key、Fake Provider**。
- `src/autoteacher_m0/security/gates.py`：`LiveGate.inspect` 永远 `BLOCKED`，`require_live` 永远抛出 `SecurityBlocked`。
- `src/autoteacher_m0/security/live_controller.py`：`TrustedLiveController` **inspect-only**；`ALWAYS_BLOCKED_REASONS` 中独立人类授权、Credential Broker、外部 Egress Proxy、Watchdog 都未部署；无真实执行入口。
- `src/autoteacher_m0/security/{authorization,ed25519,credential_boundary,watchdog,egress}.py` 有已有的离线代码/测试，不假设它们已经在真实 G3-D runtime 中组合运行。
- `src/autoteacher_m0/security/egress.py` 默认 `EgressPolicy` 指向 **OpenCode Go 内测路线**；G3-D 当前 `offline-test-only-g3b/fixture-bridge-v1` 是 synthetic route。这两者**都不是已验的官方 DeepSeek 正式主路由**。
- `docs/E5_PRELIVE_NO_KEY_REPORT.md` 只证明早期 E5-P01..P05 逻辑子集，整体 E5-PreLive **NOT PASS**。
- 规划主模型为 DeepSeek V4.1 Flash；**准确模型 ID、API endpoint、Streaming/Usage/价格/限流/供应商侧预算可用性都尚未在本轮受信验明**，不得硬编码未经核实的值。

### 0.2 明确的非目标

- 不部署真实 API Key、Secret Manager、供应商账户/付款、付费 HTTP 或 provider DNS/TLS；不在 Host/Agent 环境试探现存 Key。
- 不实现会被 CLI/插件/Env 打开的 Live allow 分支；不编辑 `scripts/run_live.sh` 为非 `exit 3`；不改 DSH adapter 的 `_require_live_authorization` 为放行。
- 不把自签的测试 Authorization 当作独立人类批准；不让 Agent 生成正式审批密钥或把私钥提交仓库。
- 不改写 G2/G3 冻结 Packet、历史 Review、原始 Trace；只允许新文档增量说明。
- 不做新的 Model Benchmark、多模型选择、教师行为/E4 成效测试；G5/G6 以后才做。

---

## 1. G4 的真正成功定义

G4 本轮不是“终于发一次真的 API 请求”，而是把 **G3-D 的可信无 Key 沙箱**与 **G4 的独立审批、只读冻结、可信准入、模拟可计费出口、撤销、外部监管** 组合到一条可审阅的执行链中，并证明任何缺失都保持阻断。

### 1.1 唯一允许的数据流（本轮）

```text
[外部维护者控制域：未部署，独立于 Agent 的未来人工决策]
           └── reviewed manifest / trusted keys / revocations / explicit authorization
                          └── 本轮只有 synthetic fixture 的验证副本
[Host-controlled no-key test launcher & watchdog]
   ├─ 根目录可写性、权限、Stage/依赖/Registry/Policy hashes（独立读取）
   ├─ 测试授权 verifier（签名和绑定；只做准入诊断，不开启 Live）
   └─ [G3-D Trusted Controller / Budget Broker / Egress Boundary]
         ├─ per-call Prepare + CallIdentity + Reserve + Bound Claim
         ├─ ATTEMPT_STARTED 持久化，再进行模拟 provider send
         ├─ Record Receipt / Usage / Observation / Settlement (or PENDING)
         └─ [Trusted synthetic transport → Fake Provider，0 Key/0 Internet]
                   ▲
                   │ 唯一受限 AF_UNIX Bridge
          [G3-D Candidate / Real DSH / skill_lookup]
          仅 candidate session 可写；无 Broker/Policy/Key mount；禁网
```

**边界判断**：G3-D 正向链的安全性必须始终成立；`ExecutionAuthorization` 的 Python verifier 通过 ≠ 人类授权安全根已部署；在 current `LiveGate` 恒 BLOCKED 前提下可以验证 **拟定 G5 的准入组件/决策**，不能把可测 `would_allow=true` 结果映射为可计费权限。

### 1.2 三种保证不可混为一谈

1. **Local accounting bound**：可信 Broker 对准备发送的每次请求预留最坏费用，unknown 保守 hold。
2. **Provider/organization budget guard**：供应商账户额度、硬封顶、停用、Key 权限（本轮仅产出待维护者核验表，不能声称已设置）。
3. **Actual invoice/settlement**：远端原始 Usage、计费记录、最终账单（本轮 0 live，不可证明）。

`config/budgets.yaml` 的 `$3` soft、`$10` engineering hard、`$0.20/call`、最多 50 live requests 是**既有策略配置**，不是云厂商强制上限；不能把它们写成“实际不会超过 $10”。本轮 synthetic suite 只验证在当前 fixture 费率下 Bound/Stop 的可验证行为。

---

## 2. 运行/任务分工与 Gate

| Gate | 实施者 | 条件 | 出口裁定 |
|---|---|---|---|
| G4-00 Rebaseline + Decisions | Lead 只读，环境 Agent 取证 | 最新 SHA、授权规则、残余登记 | 可继续无 Key |
| G4-A Trusted Approval Contract | Auth Implementation Agent | 复用 `authorization.py`，确认独立 OS 域、撤销与 strict parser 负例 | `A_TESTED`，不发布真审批 |
| G4-B Frozen Inventory & Actual Registry | Runtime/Config Agent | 实际 DSH profile/merged registry/tool/依赖/配置哈希，漂移 fail-closed | `B_TESTED` |
| G4-C Trusted Synthetic Egress | Bridge/Accounting Agent | G3-D 正向+拒绝、完整账本、模拟发送无 fallback | `C_TESTED` |
| G4-D Watchdog/E5 No-Key | Reliability/Security Agent | 进程树 kill、E5-P01..P05 离线子集、Key sentinel 不泄漏 | `D_TESTED` |
| G4-E Packet & Independent Review | Evidence Agent + 独立 Reviewer | 源码 diff/动态 Probe/两轮回归/证据哈希 | `PASS_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE` 或 FAIL/BLOCKED |
| G4-H Human-controlled Deployment | **维护者，不是 Agent** | 真密钥/供应商/部署/授权签名/网络/真实策略 | **本轮 NOT AUTHORIZED** |

### 2.1 P2 维护者待决，不因继续本轮而默认批准

- **P2-DISK**：Candidate session 绑定宿主目录，没真实磁盘硬配额；允许无 Key G4 模拟测试，但进入任何**凭据联网的长期运行**之前要求配额或选择更强隔离，并留下压力与恢复证据。
- **P2-USERNS**：允许嵌套 User Namespace；当前未发生越权。无 Key 可暂时接受本机风险；真实 Key 前维护者必须选择额外 seccomp/禁 userns 或明确签收风险。
- **P2-RUN-IDENTITY**：`SO_PEERCRED` 只能鉴别 UID，不区分拿到同一路径的同 UID 旧 Run。G4 无 Key 必须做一组“知道路径/同 UID”恶意负例和 nonce/Admission/epoch/replay 协议审计；是否加强 per-run capability/独立 UID 应依据结果和维护者决定，**不能冒称已有 per-run OS 身份**。
- 其他保留：没有 real-DSH same-claim、Broker 自身 crash/restart、长期持续接单、跨机器适配的充分证据；属于未来主张的强制限制，不需要全面重做 G3-D。

---

## 3. G4-00 — 冻结身份与当前能力矩阵

### 3.1 Read-only 输入

必须读取：`AGENTS.md`、`SECURITY.md`、`SECURITY_APPROVALS.md`、`docs/REVIEW_G3D_INDEPENDENT.md`、`docs/M0_G3D_REVIEW_ERRATA.md`、`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md`、`docs/E5_PRELIVE_NO_KEY_REPORT.md`、`docs/Autonomous_Teacher_M0_G2L11_to_G6_Agent_Playbook_2026-11-16.md`、`docs/M0_REQUEST_BINDING_CONTRACT.md`、上述 security 模块、`src/autoteacher_m0/bridge/**`、`scripts/g3d/**`、`config/dsh/**`、`plugins/**`、`config/budgets.yaml`。

### 3.2 基线输出（不能只写 HEAD）

- `base_sha`、全部父提交链、worktree 是否干净；旧 `cf40c6b` 与新 HEAD 的 code/config/docs diff，是否有冲突文件。
- Runtime DSH/Node/Python/Podman/crun/kernels、Rootfs/Deps/Stage/Adapter 的 **canonical hash**；**从已运行进程中读取** `inspect.getfile` 或等价模块证据，不能只列 Stage 文件。
- Host、Trusted、Candidate 的实际 uid_map/gid_map、Mountinfo、network/capabilities、UDS owner/mode、`SO_PEERCRED` 与 userns 差异。
- 当前 LiveGate、`scripts/run_live.sh`、CLI `--live`、Runtime Adapter 入口的**动态负例**，所有真实计费调用数必须为 0。
- 现有授权/Watchdog/Controller 组件实际是否生产调用：`implemented` / `tested in isolation` / `wired into actual trusted process` / `externally deployed` **四列分开**；没有调用就标未集成。
- Prompt/私钥/真实 Key/env/token 扫描只做安全正则与文件/环境清单，**不得读取或输出 Secret 原文**；不要扫描敏感宿主目录来“证明没有 Key”。

### 3.3 STOP

环境 hash 漂移且不能定位、Stage 加载旧 G3-C、Candidate 可写 state、旧绕过重新成立、Runtime 有网络、LiveGate 非 BLOCKED、权限异常、凭据痕迹泄漏 → **STOP_AND_REPORT**。

**G4-00 交付**：`docs/M0_G4_00_BASELINE.md`、`artifacts/g4/baseline/{identity,env,module-map,gate,negative-summary}.*`、SHA 及来源。

---

## 4. G4-A — Trusted Approval Contract / Key Root（无真密钥）

### 4.1 目标与代码边界

以现有 `src/autoteacher_m0/security/{authorization.py,ed25519.py,live_controller.py}` 为基础，**不得新建相互矛盾的授权格式**。`ExecutionAuthorization` 使用 `at-m0/execution-authorization/v1`、`ExpectedBindings`、allowed tools、route、budget、deadline、签名、revocation、expiry；`TrustedLiveController` 目前 inspect-only。G4-A 只补离线检查、组合调用与失败关闭接口（如确有实际缺口），不改成 `run()` 可发送。

### 4.2 信任根与人类职责分界

- 真实批准公钥、撤销文件、签名授权文件 **未来必须**放在 Agent 不可写的外部权限域；测试中只能使用 `TEST_ONLY_` 命名的合成 Ed25519 预制 fixture，私钥绝不进入 Candidate/真实部署镜像。
- 私钥不得由授权 API、Candidate 或 Controller 暴露生成/保存能力；`ed25519.sign()` 的 test-only 用途只用于离线测试，运行时可信组件中不得可调用到正式签发路径。
- `trusted_keys` 必须拒绝 Ed25519 非法、小阶、带 torsion、公钥非 canonical、签名 R 非 prime order、S 越界、短长签名；不因 `verify()` 失败抛 traceback 而开放权限。
- 授权 JSON 重复 key、NaN、Infinity、bool-as-int、float-as-int、unknown fields、未知 route/model、工具白名单变化、过期、未生效、撤销、重放/重复 authorization_id → 逐条 fail-closed。
- 授权允许的 SHA 必须包含真实有执行影响的完整 input closure：trusted controller、broker、egress、candidate adapter、实际 tool registry、merged profile、runtime/deps、price/budget/route policy、Stage，不能由 Candidate 自选一个不完整清单让自己通过。
- **允许测试 verifier 返回 `approved=true`，但系统行为仍必须由上层 `LiveGate`/未部署信任根阻断。** 合法合成签名不能导致 real dispatch；测试报告分列 `signature_valid` 和 `billable_send_authorized`。

### 4.3 绑定 SHA 与 TOCTOU

基线检查应基于独立构建/复算 manifest，校验签名前后代码、merged profile、socket/mount、运行版本一致；关键部署文件只能由 Launcher 在可信 OS 域以只读方式提供。代码/registry/dependency/route/budget/expiry/revocation 任一变化必须立即阻断新 dispatch；已有 `ATTEMPT_STARTED` 的 Usage/成本按 G3-C/D 保守恢复，不因撤销伪造 FREE。

授权后发生修改时，不应只在启动时检查一次：必须验证至少 **启动前**、**每次 Reserve 前** 与**每次 Egress Dispatch 前**的权威绑定（或证明不可修改的强 OS 保证加缓存版本逻辑）。需要解释竞态窗口如何封闭。

### 4.4 测试清单

- A01 正确合成签名验过，但 LiveGate、CLI、Adapter 仍阻断真实发送。
- A02 schema/duplicate key/type/unknown field 负例。
- A03 Ed25519 负例：小阶/非 canonical/混合 subgroup/短签名/S>=L。
- A04 三个独立真实文件路径（Keys、Revocations、Approval）中任何一个不可读、不安全、候选可写时 fail-closed。
- A05 SHA/config/Route/Tools/Budget/Deadline/Model 差异矩阵；禁止 float、bool-as-int。
- A06 过期、撤销、not-before、clock-skew；下次 Dispatch 的新请求拒绝。
- A07 篡改批准 Markdown、`--live`、`AT_M0_LIVE_APPROVED`、同名 env 无法授权。
- A08 合法 synthetic authorization 重放、新 run 使用旧授权 ID 的处置明确；不得自行设计无限复用许可。

**G4-A 交付**：`docs/M0_G4_A_AUTHORITY_CONTRACT.md`、变更/测试、Adversarial auth trace。最高可标 `PASS_NO_KEY_AUTH_VALIDATOR`，**不得** `HUMAN_AUTHORIZATION_DEPLOYED`。

---

## 5. G4-B — Frozen Inventory、真实 DSH Profile 和 Tool Registry

### 5.1 从“期望配置”走到“实际运行”

必须在当前 G3-D **真实 Candidate DSH 运行环境**中提取：实际已加载 Plugin/Adapter 版本、所有配置合并顺序、实际 Tool Registry/Schema、实际网络/日志/上传策略、模型配置、SDK 依赖文件 SHA。只能依赖真实 API/Trace/运行时可得的受审数据；如果 DSH `0.2.2-rc.2` 不支持导出权威 merged registry，要给出：`UNVERIFIED` + 无法证明的具体内容 + 可实施的额外外部阻断（例如 Controller 严格 Tool Schema/发送白名单），不能伪造 `registry=skill_lookup only`。

### 5.2 封闭输入清单

- 按实际构建把文件列入 `manifest.json`（relative path、sha256、size、mode、source commit）并录入 runtime/env/UID/mount/route/budget/tool-schema/price source 键；禁止依赖 Agent 选定的非完整子集。
- Manifest 自身具备确定性 Canonicalization；支持 fail-closed 的新增/删除/修改检测；**不存在**可写 Candidate 路径、临时 session 中的可执行代码、下游动态 plugin 替换未计入的漏洞。
- 真实 `skill_lookup` 注册 schema 的 SHA 与 Admission 中批准的 Tool Schema 完全一致；未经批准的 Shell、文件修改、网络工具不能进入 Controller 允许的 Provider Tool Call。Candidate 本地 tool 可以执行不等于可调用计费 Provider；必须对两者分别测试。
- DSH 的自动 compaction、summarization、judge、File/Multimodal 等可能产生 **额外 Provider 调用**的路径，逐个检查实际禁用/可观测性；若无法证明禁用，必须要求独立的 per-dispatch Reserve/Claim 兜底且做负例。
- **Log/telemetry**：验证真实运行路径关闭上传；无从证明时标 `BLOCKED`，不能只看 `session_log_disabled=true` 配置文本。

### 5.3 证据级别

- L0 静态配置检查；L1 运行时 API/Loaded Module/SDK Trace；L2 隔离 OS 负例/实际 Broker 状态；L3 真 Provider（**本轮禁止**）。
- 对 registry、SDK 动态行为至少提供 L1；对安全边界和无外发至少提供 L2；不能用 L0 代替 L1/L2。

### 5.4 测试

B01 完整 Manifest 与运行字节匹配；B02 代码变异、插件新增、Tool Schema 篡改 fail；B03 实际 merged registry / 不可证明项声明；B04 工具调用两轮各自预算绑定；B05 注入额外 Provider request 必须触发 Reserve/Claim 或零发送；B06 Logs/telemetry/网络负例；B07 不同 Worker 共享 Stage 不污染 canonical；B08 变化后撤销/基线变更仍 fail closed。

**G4-B 交付**：`docs/M0_G4_B_RUNTIME_INVENTORY.md`、`artifacts/g4/runtime/{manifest,registry,loaded-modules,probe}.*`。

---

## 6. G4-C — Trusted Synthetic Egress：唯一发送与记账路径

### 6.1 设计原则

G4-C 不应重写 G3-D 的 `controller.py` 为联网代理。优先采用**可插拔但默认 synthetic-only**的 Trusted Transport/Provider boundary；真实网络 Transport 不在本轮启动。复用 G3-D IPC 与已审的 `PreparedProviderRequest`/`CallIdentity`、Bound Broker/Attempt Journal、Receipt 验证。现有 `security.egress.EgressPolicy()` 默认 **OpenCode Go**，只能视为旧的内部测试约束；不得通过将 `offline-test-only-g3b` 指向公共网络或把 `openai`/`deepseek` 设成 wildcard 来“演示 Live”。

### 6.2 新增兼容契约（先冻结再编码）

- `ProviderRouteContract`（可命名不同，但语义必要）：`route_id, provider, model_id, endpoint_host, port, method, exact_path, request_format_version, streaming_contract, tokenizer/price_source_version, max_output_tokens, allowed_tool_schemas, retry_policy, allow_files/images/store`；synthetic fixture 与未来 real route 分开声明。
- `TrustedSendAuthorization` 必须由可信域生成，绑定 `scope/run/call_id/prepared_digest/reservation_id/broker_claim/payload_digest/length/attempt/route/model/auth_epoch/expiry`，不可直接作为 Candidate 提供的 JSON 授权；**不允许第二条未记账的 provider API 路径**。
- 先严格序列化并复算真实出站 Payload SHA，再执行 Broker 绑定 Claim，持久 `ATTEMPT_STARTED`，才允许 Fake Provider 读取字节；收据与 Usage 来源和摘要可独立核查。
- 对多次工具调用，一个 Provider `stream()` 入口对应**独立** CallIdentity、Reserve、Claim、Attempt、Receipt、Observation；不能数 `request/header` 事件。
- 异常、5xx、模拟 429、连接断开、取消、OS SIGKILL、Usage 无效、远端收据未知：均没有自动重发；出站前失败 `NOT_DISPATCHED`，可能发出的调用记 `BILLABLE_UNKNOWN/SETTLEMENT_UNCERTAIN` 等保守状态。
- 未知成本不得默认为 0；若无供应商价格或 tokenizer 的可信上界，**真实模式应 BLOCKED**；synthetic 只允许冻结费率 fixture。

### 6.3 可执行模拟

优先沿用 `scripts/g3d/launch.py`、D3 suite、Fake Provider 的现有调用链，给出一个 G4 PreLive 执行器，在 `--network none` 下用 **Fake Credential sentinel（仅测试）+ Synthetic Egress** 演示完整准入/拒绝/崩溃/结算。若要用 loopback fake HTTP，则必须明确它不是外部 Provider/真实 TLS/真实收费；可以不用新增 HTTP 服务，保持 stdio。

### 6.4 Real provider 的接口准备而非开通

- 未来官方 DeepSeek Route、API 版本、精确 URL、身份认证格式、stream chunks、tool schema、Usage、cache/token 计费、错误码、定价、限额，须有**执行 G5 当天**的官方资料和维护者审批快照；目前状态 `REQUIRES_VERIFICATION`，禁止硬编码旧 OpenCode Go 路由当正式主渠道。
- 执行 G5 必须由受信 Controller/egress 域持有专用可撤销 Key；Candidate 无 network、无 Key；同 host 的真实路由 DNS/TLS/IP 重绑定/代理 env/redirect/请求路径解析风险需要 G4-H 人工安全审查，**本轮模拟不能证明这些机制**。
- 供应商侧所谓硬额度必须由维护者核验管理后台或 API 证明，不能用 local `$10` 直接称供应商硬限。

### 6.5 必测用例

C01 完整两轮 DSH Tool → 两套账本；C02 无授权/无 Claim/Claim 已消费 → Fake=0；C03 Prepared/bytes 摘要不一致 Fake=0；C04 Route/Model/Host/Path/Method/Tools 多字段变异；C05 Broker crash/Timeout/Claim 后 SIGKILL/发送后 SIGKILL；C06 429/5xx/无 Usage/部分 Usage/重复 Usage/late Usage；C07 重放同业务身份最多一次；C08 备用 direct HTTP / fallback 绝不可调用；C09 token 上限/费用上限/软阈值/硬阈值；C10 synthetic Price/Version 缺失阻断；C11 Session Resume 保持连续性但不重发。

**G4-C 交付**：`docs/M0_G4_C_EGRESS_CONTRACT.md`、实际修改/定向测试、带独立 DB 快照与 Fake Counter 的完整 Trace。

---

## 7. G4-D — External Watchdog、撤销与 E5-P01..P05 离线组合

### 7.1 外部监管

使用现有 `security/watchdog.py` 和 `scripts/g3d` 的进程/容器清理经验。Watchdog 是位于 Candidate 和 Trusted 之外的可信监督进程，不是 Candidate 内起的守护线程，也不是只读 `elapsed()` 的诊断器；能够从外部强制 SIGTERM→SIGKILL、独立确认所有容器/子进程/UDS 清理。

必须覆盖：Controller crash、Fake/Broker hang、Candidate 提前退出、连接僵死、Watchdog 自身失败、Podman daemon 查询失败、资源上限、清理失败。`rm -f` 返回 0 不等于 absence；必须显式复查。出错时将 Reservation/Attempt 保持 PENDING/UNKNOWN，永不自动重发。

### 7.2 凭据边界（仅哨兵值）

仅允许**明显非真实的测试哨兵**，如 `TEST_ONLY_NEVER_VALID_SECRET_SENTINEL`；不从 `os.environ`、`~/.config`、真实密钥管理器查找 Key。只在 trusted 测试 fixture 中检查以下传播面：Candidate env、argv、mount、`/proc`、Session、DSH Profile、Tool Output、Crash Log、Broker 日志、Receipt、JUnit、Packet。任何一个含哨兵实际值都判 FAIL；日志脱敏检查在测试中允许比较哈希/是否包含，禁止把“已脱敏”当作唯一隔离层。

### 7.3 E5-PreLive 证据分层表（必须按表实际填写）

| Gate | 本轮能证明 | 本轮不能证明 |
|---|---|---|
| E5-P01 | 测试签名/Binding 与实际冻结字节一致、变更拒绝 | 外部真实人类签名已部署 |
| E5-P02 | 编译产物、依赖、Policy、Tool Schema 变化时模拟准入阻断 | 真实部署后所有动态文件都不可写 |
| E5-P03 | Agent 改 Markdown/env/flag/self-sign 无法开当前 Gate | 正式人类审批、独立外部 trust root 已上线 |
| E5-P04 | 真实 DSH Tool 实例、Registry/Schema SHA 可观测且受 Controller 白名单约束 | 未知的 DSH 动态 tools 全部被删除（若无法证明必须 BLOCKED） |
| E5-P05 | Synthetic Secret 跨 Mount/Env/Log/IPC 拒绝、Watchdog 清理 | 真实 Key 保护、真实出站 TLS/账单/供应商硬额 |

E5-P01..05 每项必须标两个状态：`NO_KEY_SUBSET_PASS/FAIL/UNVERIFIED` 与 `FULL_STATUS=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。禁止用统一 `PASS` 含糊覆盖。

### 7.4 强制负测

D01 Watchdog 真实进程树 kill + container absence；D02 Trusted hang/Candidate hang；D03 Candidate stdout/stderr/session/env/mount 无哨兵；D04 改授权后拒绝下一 dispatch；D05 revoke 与 in-flight unknown 保守；D06 未批准 Tool Registry/Extra Provider request 拒绝；D07 宿主 `run_live.sh`/CLI/Adapter/LiveGate 全阻断；D08 故障清理失败必须暴露 BLOCKED；D09 实际 Launch 切换 Run epoch 旧票据拒绝；D10 审查输出对用户不包含 Secret/敏感路径原文。

**G4-D 交付**：`docs/M0_G4_D_E5_NO_KEY_REPORT.md`、清理/拒绝/哨兵证据、`artifacts/g4/e5/`。

---

## 8. 独立 Reviewer 必须做的敌意审阅

Reviewer 不可只运行 Owner 测试，也不可只检查 `sha256sum -c`。至少完成：

1. 用同一冻结 SHA 自己构造失效签名、Ed25519 异常点、`bool` 限额、重复 JSON key、撤销、Runtime SHA 不匹配；确认没有任何可计费/模拟发送权限。
2. 从**真实 Candidate UID/Mount** 尝试读写可信批准 Keys、撤销文件、Policy、Broker/DB、Secret sentinel，运行 G3-B 的旧四类攻击；必须为 OS/Protocol 拒绝。Candidate 同 UID stale Run 的已知路径攻击不能被目录名随机性描述代替。
3. 运行**真实 DSH Tool 两轮**，逐一比较：两个不同 call_id、Prepared Digest 与 Claim 摘要相等、Payload SHA 与 Receipt 原始 SHA 相等、两组计费且不重发。
4. 中断 Broker/Trusted/Watchdog、SIGKILL Candidate；查看 DB 是否出现 Fee=0 或双发送，检查未完成账本可恢复但不会重发。
5. 检查 `LiveGate`/CLI/Adapter/run_live 入口的行为字节以及是否出现新 allow 旁路；任何真正可发网络/真实 Key 的路径属于 P0。
6. 用独立脚本重新解析原始 SQLite、Fake Receipt、Counter、DSH Trace、JSON/junit，而不是复用 Owner `checks.json` 的 status。
7. 将证据明确分为：real DSH/no key、raw UDS、Host/unit、static、unverified、human-required；任何跨级证据拼接为一个“全链 PASS”均要降级。
8. 复核 Packet 的 `impl_sha`, `docs_sha`, `runtime_sha`, `stage_hash`, `loaded_module_sha`、变更 diff 及哈希脚本，刻意用旧 Stage 重跑检验能否 fail-closed；不能再复现 G3-C 的 stage-old-code 错位。

Reviewer 严重等级：`P0` = 权限可绕过/可计费出站路径已放开/Key 泄漏/未授权 Fake send/账本 FREE；`P1` = 关键部署契约不一致、凭据边界失效、结算/恢复错误或核心主张缺少动态证据；`P2` = 不影响本轮限定范围的运行维护或证据卫生。不得将真实 Key 缺失误标为技术 P0；它是 **G4-H/G5 的硬 BLOCKED 条件**。

---

## 9. G4-E 冻结与 Review Packet 规范

### 9.1 必须交付的源码和文档

```text
docs/
  M0_G4_00_BASELINE.md
  M0_G4_A_AUTHORITY_CONTRACT.md
  M0_G4_B_RUNTIME_INVENTORY.md
  M0_G4_C_EGRESS_CONTRACT.md
  M0_G4_D_E5_NO_KEY_REPORT.md
  M0_G4_IMPLEMENTATION_REPORT.md
  M0_G4_FINDINGS_AND_DISPOSITION.md
  M0_G4_REVIEW_REQUEST.md
  REVIEW_G4_INDEPENDENT.md              # 由不同 Reviewer 完成
  M0_G4_HUMAN_HANDOFF.md                 # 未签署、只列人工操作与待证据
artifacts/g4/                          # gitignored，完整本地运行证据
artifacts/review-packet-g4-<implSHA>/   # 冻结的脱敏包；附 hash/manifest
```

新代码布局由 Lead 根据现有 `src/autoteacher_m0/security/` 与 `scripts/g3d/` 选择**最小**增量；不得仅为了满足以上目录创建无必要新类。每个 Commit 按 `G4-A/...` 等 work package 分开，Docs 与实现分开提交。

### 9.2 Packet 必备字段

`schema_version, base_sha, impl_sha, docs_sha, build_sha, source_blobs, rootfs_sha256, deps_sha256, stage_manifest_sha256, runtime_sha, actual_loaded_modules, provider_route_kind=synthetic_only, real_model_calls=0, real_external_http_calls=0, key_present=false, live_gate=BLOCKED, evidence_levels, case_statuses, residual_risks, reviewer, previous_review`。

至少包含：完整 diff/源码摘要、Manifest 和源码 Blob 验证脚本、执行命令 `argv.json`、UTC、exit、DSH/Broker/Receipt 对账、负例与失败日志、Secret sentinel 扫描、E5-P01..05 的**两列状态**、修复前 RED/后 GREEN、Host/OCI/Node 适用性、旧证据不可变性声明。

禁止：真实 Credential、自动化 Token、真实账单/审批私钥、用户 Session 原文、宿主个人路径、未经脱敏的日志。若 Packet 包含源自运行容器的 1000+ 文件，必须审核其源闭包及来源，**不要为增加文件数而重复复制目录**。

### 9.3 可接受的最终 Gate 状态

- `PASS_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE`：工程/隔离/模拟账本/授权校验/E5 无 Key 子集被独立复验，无 P0/P1；**不代表 E5-PreLive Full**。
- `PARTIAL_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE`：功能有证据但重要项未验证；列出缺失测试和真实原因。
- `FAIL_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE`：能复制的安全或账本反例。
- `BLOCKED_NEEDS_ENVIRONMENT`：无法构建真实 OS 隔离/受审 Runtime，不许 mock 替代。

所有状态都附：`G4-H=NOT_AUTHORIZED`, `G5=BLOCKED`, `G6=NOT_RUN`, `LiveGate=BLOCKED`, `M0=DECISION_PENDING`。

---

## 10. 本轮绝对 STOP 条件

**出现以下任何情况必须立刻停止并报告具体 SHA/时间/测试 ID：**

- 任何真实 Key、账户 Cookie、供应商 Secret 被读取/注入/输出，或任一公共 HTTP/TCP 与真实 Provider 交互。
- `run_live.sh` 不再 exit 3；`LiveGate.require_live()` 可以返回成功；CLI/Adapter 增加绕过审批的开关；Synthetic Authorized 被映射到 billable send。
- Candidate 读写 Broker/Policy/Approval/Revocations/Key；候选在 Controller 外调用 Provider；Fake 已收但 Journal 是 FREE/NOT_DISPATCHED 或无 Attempt。
- 固定源码/runtime/schema hash 偏离，实际加载旧源码；批准文件、Route、Tools、Price Policy 变了却未使下一次 dispatch fail-closed。
- Uncertain Usage/cancel/crash 后重复发送或没有保守账本；Watchdog 失效却继续运行。
- 证据有真实 Secret/个人 Session/评估标签，或 Reviewer 是 Implementation Agent 本人。

STOP 后只允许完成现场证据保全/安全清理；不得为了“让测试绿”临时 `chmod 777`、开放 TCP 或启用 Host fallback。

---

## 11. 人类维护者专属的 G4-H 检查表（**不授权 Agent 实施**）

这是一张**未来行动清单**，不构成本轮自动执行任务：

1. 对精确冻结提交及全部运行依赖/工具/配置/路由/预算做独立二次审阅，必要时另开安全复核；任何代码/配置修改使旧授权失效。
2. 在 Agent 不可写权限域中**由人类**创建/保护实际审批信任根，定义 Ed25519 公钥注册/轮换/撤销、私钥离线保管、一次性授权范围和有效期；不得复用测试私钥。
3. 选择独立 Key Broker/可信 Egress 的部署与网络策略；只让可信 Egress 有出口、最小权限 Key 和 DNS/TLS 验证，Candidate 永久禁网；检查 redirect/proxy fallback/extra POST。
4. 核实当日**官方** DeepSeek 模型 ID、Endpoint、价格、Usage 字段、Tool/Stream 兼容、Provider 侧额度与 Key 作用域；若不支持实际硬封顶，必须给出可信出口风险限额、降级计划及人工接受风险，不能承诺硬预算。
5. 决定并签收 G3-D P2：Session 磁盘硬配额、嵌套 userns、同 UID old Run；如要长期运行，补长稳/磁盘压力并取证。
6. 独立执行 E5-PreLive 全项真实部署验证，并由不同于 Implementation Agent 的 Security Reviewer 出具正式 PASS；只通过 G4 无 Key 子集不允许使用 Key。
7. **仅在以上全部通过后**，维护者另发一次范围严格限定的 G5 试验授权，明确具体 route/model、单次 run、时间、总调用上限、费用限额、Watchdog、撤销和负责人；G5 再按 Smoke/Tool/Session 分批人工审阅。

当前所有项目标记：`PENDING_HUMAN_ACTION`，不得由 Agent 在 Markdown 中写“APPROVED”替代真实授权。

---

## 12. 推荐提交顺序与避免无效返工

1. **G4-00**：先查已有实现，逐模块标 `reuse/revise/not wired`；不要直接生成 1000 行新授权框架。
2. **G4-A + G4-B**：可并行，只读运行时证据先于合并测试；A/B 的 Binding Manifest 契约由 Lead 冻结。
3. **G4-C**：在真实 G3-D 双 Principal 上加入 synthetic-only trusted send 组合测试；不创建额外网络 Provider。
4. **G4-D**：只复用已有 Watchdog/Guard，增量补外部进程树监管与 E5 准入负例；与 C 交叉测试。
5. **G4-E**：Lead 做统一冻结、委派独立 Reviewer；Reviewer 必须有自己的 Probe 和账本对账。
6. 收到 PASS 才允许**发起新一轮维护者决策**；没有决策之前 G4-H、G5、G6 一律不能推进。

若 G4-00 发现已有授权/Widget/Runtime 校验已完全覆盖某项，直接附真实代码调用与独立动态证据，标 `REUSED_VERIFIED`；**不要机械重复实现**。

---

## 13. 矩阵填写与证据约定

随包 CSV 是测试 ID 的**初始矩阵**，所有行 `NOT_RUN`。每条完成时填写：`gate,case_id,priority,level,expected,actual,status,command_argv,utc_start,utc_end,exit_code,impl_sha,stage_sha,source_blob_paths,log_paths,db_receipt_paths,residual,reviewer_status`。同一案例可分 `SIMULATED PASS` / `REAL UNVERIFIED`，不得合写成一个 `PASS`。采用固定路径，原始日志和独立对账脚本必须留在 gitignored artifacts 目录；提交只含脱敏索引与报告。

状态词：`PASS`（该层真实执行满足断言）、`FAIL`、`PARTIAL`、`UNVERIFIED`、`BLOCKED`、`NOT_RUN`、`N/A_REASONED`。**E5 FULL** 单独列在矩阵中并默认 `BLOCKED`，直到维护者后续新授权；不允许为了所有行变成 PASS 而伪造签核。

---

## 14. Lead 独立验证与 Reviewer 交接要求

Lead 先执行静态 Diff 归因、实测环境清理/哈希、定向回归、全量 OCI（显式报告 Skip/Deselect）、Guard/Skill Node、LiveGate 负例，然后交独立 Reviewer。Reviewer 至少重跑 A02/A03/A05/A07、B02/B04/B05、C01/C02/C03/C05/C07、D01/D03/D04/D06/D07，并独立复核 E5 两列状态；若环境限制真实重跑，必须标 `UNVERIFIED`，不据此裁定 FULL PASS。

报告中必要的定量断言：`real_provider_calls=0`、`real_external_http_calls=0`、`provider_keys_seen=0`、`billable_send_allowed=0`、`LiveGate.status=BLOCKED`、测试 Fake counter 与 ledger 调用数一致、所有无 Claim/权限拒绝 Fake counter 不增长。

结算要校验 **两对不同的摘要**：

```text
PreparedProviderRequest.request_digest == BrokerClaim.request_digest
Attempt.payload_digest == FakeReceipt.raw_sha256
Prepared Digest != Payload Digest     # 正常情况下不同；不是同一摘要
```

上述是常见期望，不得把两摘要不相等当成必要密码学条件；真正断言是两组正确映射与数据/字节逐项一致。

---

## 15. 最终交付请求与 STOP

交付 `docs/M0_G4_REVIEW_REQUEST.md`，至少提供：冻结 Git SHA、真实加载 modules、改动文件、每个 Gate 的测试通过/失败/未运行、E5 P01..05 双层状态、原始证据路径、Packet Manifest/Hashes、独立 Reviewer Findings、长期残余与需要维护者决策项。

**G4-E 独立 Reviewer 出具限定范围裁定后必须 STOP。不能把“无 Key 工程 PASS”当作人类授权部署 PASS，不能自动触发 G5。**

---

## 16. 可直接复制给 Lead Agent 的总指令

> 阅读 `AGENTS.md`、本任务书全文与矩阵，以及本任务书开头指定的 G3-D/G4 安全基线。你是 Lead，只组织/审核/验证；把实际实现委派给独立 Agents。先核对 GitHub 实际 HEAD（参考 `017c7476...`），冻结基线，保留旧历史；把已有授权、Watchdog、Egress 模块分成复用/增量/未接入，禁止重造。
>
> 严格依次执行 G4-00 → G4-A/B → G4-C → G4-D → G4-E。所有测试保持无真实 Key、无真实 Provider、`--network none`、正式 LiveGate BLOCKED；synthetic signing、synthetic credential 和 fake transport 仅用于测逻辑，不能构成真实权限。
>
> 以真实 DSH + G3-D 双 Principal 跑通工具两轮、Session Resume、Budget/Claim/Attempt/Receipt；补真实 Registry SHA、配置漂移、Authorization/Ed25519/revocation 负例、模拟 Egress 故障、Watchdog 外部清理、E5-P01..05 两层状态。每条必须给原始命令、时间、退出码、账本、证据 SHA；完整矩阵从 NOT_RUN 开始逐项更新。
>
> 冻结实现后委派未参与开发的 Reviewer 自建攻击和账本对账。要求 Review Packet、自身测试日志和有限范围裁定。没有独立 Reviewer PASS 则不能宣称工程通过。不得启用 G4-H/G5/G6，不得自行部署真实授权/Key/网络，不得在 CLI/Script/Plugin 中增加放行开关。**完成本轮提交并 STOP，等待维护者审阅。**

---

*维护者注意：本文件只授予 no-key engineering，没有授予任何实际人类信任根、凭据部署、模型计费或 Live 权限。*
