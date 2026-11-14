# 可信 Live Controller — 安全设计（PR3，无 Key）

- 任务：`task-36`（v0.5 PR3）；基线 `HEAD=e8b6e45b19d9001231323c76bc71fa4886be3439`
  （文档提交）；被测实现 SHA 仍 `feb7118f9aff20c681cc651812b30315288080f1`
- 状态：**设计 + 无 Key 故障验证完成；不授予 Live；所有真实 Live 入口保持 BLOCKED**
- 证据：`artifacts/m0-controller-no-key/`（argv/UTC/exit/镜像身份/测试日志/hash）
- 关联：[`M0_REVIEW_FINDINGS.md`](M0_REVIEW_FINDINGS.md)（F3/F7/F8/F10）、
  [`M0_CLOSEOUT_DECISIONS.md`](M0_CLOSEOUT_DECISIONS.md)、
  [`OPENCODE_GO_ACCESS.md`](OPENCODE_GO_ACCESS.md) §4、
  [`E5_PRELIVE_NO_KEY_REPORT.md`](E5_PRELIVE_NO_KEY_REPORT.md)

> 本设计不读取真实凭据、不调用模型、不发起真实 HTTP；测试中仅使用**假 Key**与
> mock/hung 子进程，且全部在固定 digest、禁网、只读、非 root 的 OCI 内执行。

## 1. 目标与不可妥协的边界

PR3 要解决的是“Live 之前由谁、用什么不可伪造的证据，阻止 Agent 自己打开 Live”。
对应源码发现：

| 发现 | 本设计的回答 |
|---|---|
| F3 后置 digest 只是检测，不是发包点费用上限 | Controller 在 dispatch **之前**校验绑定/预算/路由；真实费用边界留给 PR4 egress/Key Broker，PR3 不宣称已解决 |
| F7 插件没加载时 Guard 无法自救 | 外部 Controller + Key/egress 边界才是第二层；DSH/候选没有真实 Key 与直连网络（PR4 部署） |
| F8 config→spawn→broker 双读 TOCTOU | Controller 记录只读 mount/哈希身份；要求 profile/config 由可信只读挂载并在启动前冻结（部署项，PR4 验证） |
| F10 无总 watchdog/进程清理 | 本 PR 提供 ExternalWatchdog：总 deadline、step/dispatch 上限、进程树 kill、容器 absence 确认、异常后 PENDING 保守、不重试 |

不可妥协项：

1. 任何 Markdown 批准、环境变量、`--live` flag、自签/仓库内 JSON 都**不能**解锁 Live；
2. 候选 Runtime/容器**永远没有真实 Key**、默认禁网；真实 Key 只由仓库外 launcher/Key
   Broker 持有，egress 只经获批 Proxy（PR4 实现，PR3 只做设计约束与负测）；
3. 授权必须绑定精确 code/lock/runtime/plugin/merged-profile SHA、批准路由/模型、工具
   白名单、预算 scope/单次/总上限、总 deadline、有效期与撤销状态；
4. 未知/超时/异常结果一律 **PENDING_CONSERVATIVE**，不自动重试 billable attempt；
5. 本 PR 完成后 LiveGate 仍恒 BLOCKED，`scripts/run_live.sh` 仍硬停，
   `HarnessAdapter._require_live_authorization()` 仍恒拒绝。

## 2. 组件与信任边界

```
维护者（仓库外）
  ├─ Ed25519 私钥：离线保管，只签 ExecutionAuthorization
  ├─ trusted-keys.json（公钥）：仓库外，Controller 只读加载
  └─ revoked.json（撤销列表）：仓库外，Controller 只读加载
             │
             ▼
可信 Controller（本 PR 设计/接口；尚未部署为 Live 授权）
  ├─ authorization.py：schema/绑定/路由/工具/预算/时限/签名/撤销，fail-closed
  ├─ credential_boundary.py：候选 env 白名单、假 Key 负测、log 脱敏、mount/egress 策略
  ├─ watchdog.py：总 deadline、step/dispatch、进程树 kill、容器 absence、PENDING
  └─ live_controller.py：只 inspect，无 run/execute 方法；永远返回 BLOCKED
             │（PR4 才可能新增受审 egress/Key Broker 与执行路径）
             ▼
候选 Runtime/容器：无真实 Key、--network=none、只读、非 root、无 host home/socket
```

信任假设与限制：Controller 自身代码/依赖尚未独立审阅，Ed25519 私钥保管与公钥部署属于
**人类部署项**；`cryptography` 不在锁定镜像依赖中，故采用零依赖 RFC 8032 实现（仅公钥
验签在 Controller 路径使用，测试用签名函数不进入 Controller）。OS 级互斥、只读挂载
强制执行、真实 egress 边界仍由 PR4/维护者验证，本 PR 不宣称具备生产级隔离。

## 3. ExecutionAuthorization（不可由 Agent 自签）

### 3.1 文件与来源约束

- 授权文件必须是**仓库外**绝对路径、非 symlink、普通文件、≤64 KiB；
- trusted keys 与 revocation 状态同样必须在仓库外；缺失/不可读 → 直接拒绝；
- `.md`/内容以 `#` 开头的文件拒绝；重复 JSON key、非 finite 数字、未知字段拒绝；
- 环境变量、`--live`、`SECURITY_APPROVALS.md`、自签 JSON 不进入任何校验分支。

### 3.2 字段（`at-m0/execution-authorization/v1`）

| 字段 | 要求 |
|---|---|
| `schema` | 固定 `at-m0/execution-authorization/v1` |
| `authorization_id` / `approver` / `approval_note` | 非空；ID 仅限 `[A-Za-z0-9._:-]{1,128}` |
| `issued_utc` / `not_before_utc` / `expires_utc` | RFC3339 UTC；issued≤not_before<expires；生命周期≤24h；签发≤7 天前 |
| `bindings` | 精确绑定 `code_sha256`、`lock_sha256`、`runtime_sha256`、`plugin_sha256`、`merged_profile_sha256` |
| `route` | `{route_id, provider, model}` 必须与 Controller 预置的**唯一**批准路由逐字段相等 |
| `allowed_tools` | 非空、无重复、⊆{`skill_lookup`}，且与实际 registry **完全一致** |
| `budget` | `scope` 匹配；`per_call_cap_usd ≤ total_cap_usd ≤ 10`；`max_calls ∈ [1,50]`；金额为十进制字符串（禁 NaN/浮点） |
| `deadline` | `total_seconds∈[1,3600]`、`max_steps∈[1,200]`、`max_dispatch_attempts∈[1,50]` |
| `signature` | 仅 `ed25519`；`key_id` 必须存在于仓库外 trusted keys；对“除 signature 外字段的 canonical JSON”验签 |

任一字段失败 → `AuthorizationDecision(approved=False, reasons=...)`；
`require_execution_authorization()` 抛 `SECURITY_BLOCKED`，无部分批准、无重试、无 fallback。
实现：`src/autoteacher_m0/security/authorization.py`、`ed25519.py`。

## 4. 凭据边界（候选容器零 Key）

### 4.1 环境与日志

- 候选 env **只**从 `CANDIDATE_ENV_ALLOWLIST`（PATH/HOME/LANG/LC_ALL/TZ/PYTHONPATH/
  PYTHONDONTWRITEBYTECODE）重建；任何 secret 命名（`*_API_KEY`/TOKEN/SECRET/PASSWORD/
  CREDENTIAL/PRIVATE_KEY）或含 secret 值的项被丢弃并记违规；
- `LauncherOnlySecret` 的 `repr/str` 永远 `[REDACTED:n]`；只有可信 launcher 可拿
  `for_launcher_env()`；
- `redact_secrets()` 覆盖已知值及 `oc_sk_`、`sk-`、`Bearer` 模式；
  `assert_log_clean()` 用于测试/审计。

### 4.2 Mount/进程/网络

- 候选 mount 仅允许 Controller 创建的公开 stage，**read-only**，目标固定 `/input`；
  禁止 `/root`、`/home`、`.config`、`credentials`、`.env`、`.ssh`、`.dsh`、
  Runtime socket、仓库源码等；
- 候选 argv 必须包含 `--network=none`、`--read-only`、`--cap-drop=ALL`、
  `--security-opt=no-new-privileges`、`--user=65534:65534`、`--unsetenv-all`、
  `--http-proxy=false`；禁止 `--privileged`、端口发布、任意 `--env`、socket/root mount；
- 现有 `ContainerRunner` 生成的命令通过该策略（用于复用而非第二套 runner）。

### 4.3 OpenCode Go 预留约束（INTERNAL-TEST-ONLY，不执行）

`OPENCODE_GO_EGRESS` 固定：host 仅 `opencode.ai`、port 仅 `443`、method 仅 `POST`、
path 前缀仅 `/inference/go/`。设计上：

- `OPENCODE_API_KEY` 只存在于**仓库外 launcher/Key Broker**，候选 env/argv/日志不可见；
- 候选容器保持 `--network=none`；真实 egress 由 PR4 的受控 Proxy 发出，且只允许上述
  host/port/path；任意通用 URL 代理、直连 DeepSeek官方域名、其他 host/端口一律拒绝；
- 真实 smoke 前置与预算/usage 约束见 `OPENCODE_GO_ACCESS.md` §4；本 PR 不执行任何调用。

## 5. 外部 watchdog

`src/autoteacher_m0/security/watchdog.py`：

- `WatchdogPolicy`：总 deadline、`max_steps`、`max_dispatch_attempts`、终止宽限、poll；
- 超时/超 step/超 dispatch → latch 状态 → **kill 进程组 + /proc 后代树**（SIGTERM→宽限→
  SIGKILL），确认 survivors 为空；否则 `SECURITY_BLOCKED`（不允许“带病”继续）；
- 容器清理必须**观测到 absence**：`rm --force` 后独立 `ps --all --filter name=^…$` 为空且
  rc=0；`rm` 的 rc=1 不被当作 absence 证明；
- 超时/异常/非零退出 → `PendingConservative(retry_allowed=False, worst_case_reserved=True)`；
  绝不自动重试未知 billable 状态；
- Controller 外壳异常时也必须在 `except` 路径 kill 进程树，避免候选遗留。

## 6. 复用现有 gates/runner，且无第二条 Live 路径

- `LiveGate` 未改动：`inspect()` 恒 `BLOCKED`（`EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`）。
- `TrustedLiveController` **没有** `run/execute/launch/approve` 方法，只有
  `inspect()`/`require_live()`；即使外部签名授权完全有效，`inspect()` 仍追加
  `EXTERNAL_CREDENTIAL_BROKER_NOT_DEPLOYED`、`EXTERNAL_EGRESS_PROXY_NOT_DEPLOYED`、
  `EXTERNAL_WATCHDOG_NOT_DEPLOYED_REHEARSAL_ONLY`、`LIVE_GATE_CLOSED`，状态恒 `BLOCKED`。
- 现有 Live 入口审计（`assert_live_entrypoints_blocked()` + 运行时负测）：
  - `scripts/run_live.sh`：`exit 3` 硬停，无 Key 读取；
  - CLI `smoke --live`：在 import/目录创建/凭据检查前返回 `BLOCKED/3`；
  - `HarnessAdapter._require_live_authorization()`：恒抛 `SECURITY_BLOCKED`；
  - `LiveGate.require_live()`：恒拒绝。

## 7. 负测矩阵（本 PR 实际执行）

全部测试在固定 digest `localhost/autoteacher-local-oci@sha256:62d3569e…64667b`
（image id `56db1e2a…`，Python 3.11.15，pytest 9.2.0）内、`--network none`、只读、
非 root、无 host home/socket 运行；宿主机不执行 pytest。结果：**104 passed, 1 skipped**
（skip 为既有 `/input` 外部探针契约，与本 PR 无关）。Ruff：**PR3 scoped**（`src/autoteacher_m0/security tests/unit/security tests/integration/sandbox scripts`）`All checks passed!`；当时 **repo-wide** Ruff 仍因既有/后续文件的未用 import/赋值未通过，已由 V-PR3-1 修复（commit `fix: closeout ruff hygiene (V-PR3-1)`，详见 `artifacts/m0-controller-no-key/manifest-errata.json`）；修复后 repo-wide `All checks passed!`，PR3 安全负测结论不受影响。

| 类别 | 关键负测（测试文件） | 期望/结果 |
|---|---|---|
| 授权来源 | 仓库内 JSON、symlink、Markdown、未知/缺失字段、重复 JSON key（test_authorization） | 全部拒绝 |
| 人类签名 | 未知 key_id、错误 seed、签名后篡改、无签名（test_authorization） | 全部拒绝 |
| 绑定 | 5 个 SHA 任一不匹配、route/model、工具 registry、budget scope、金额/次数/时限越界（test_authorization） | 全部拒绝 |
| 有效期/撤销 | 过期、未生效、过期太久、>24h 生命周期、撤销文件缺失/命中（test_authorization） | 全部拒绝 |
| 环境/flag | env `AT_M0_LIVE_APPROVED` 等 + 仓库 Markdown 无授权文件（test_authorization） | 不能解锁 |
| 凭据 | 假 `OPENCODE_API_KEY`/`DEEPSEEK_API_KEY`/token/proxy 不进入候选 env；日志脱敏（test_credential_boundary） | 全部拦截/脱敏 |
| mount/argv | rw/root/home/repo mount、`--privileged`、端口发布、危险 `--env`、缺隔离 flag（test_credential_boundary） | 全部拒绝 |
| egress | 非 opencode.ai、非 443、非 POST、非 `/inference/go/`（test_credential_boundary） | 全部拒绝 |
| watchdog | hung 子进程/孙进程 timeout、step/dispatch latch、非零退出、清理异常（test_watchdog） | kill 树+确认 absence+PENDING+不重试 |
| 容器清理 | 残留容器、`ps` 失败、`rm` rc=1（test_watchdog） | 只在观测到 absence 时通过 |
| Live 入口 | CLI `smoke --live`、`run_live.sh` 静态硬停、Adapter LiveGate、仓库审计（test_live_controller_no_key） | 全部 BLOCKED |
| 端到端 | 有效外部签名授权 → Controller 仍 `BLOCKED`；假 Key 不泄入 audit/candidate（test_live_controller_no_key） | 不解锁、不泄漏 |

## 8. 仍 BLOCKED / 需要人类或后续 PR

1. **E5-P03 / 真实人类授权边界**：Controller 尚未以独立 OS 身份部署，Ed25519 私钥/公钥
   托管、仓库外撤销机制、只读挂载强制均需维护者独立审查与部署。
2. **PR4 egress/Key Broker**：候选禁网、Proxy host/port/path 白名单、请求级预算/usage、
   billable-path inventory 尚未实现；因此真实费用上限仍是 `BLOCKED`（不得宣称硬预算）。
3. **真实 Runtime/Profile/工具 registry**：merged profile、插件版本/加载失败模式、实际
   工具注册表、DSH session-log 上传禁用需在 PR2/PR5 用真实合并配置验证（本 PR 只做接口）。
4. **真实 Provider wire 行为**：真实 401/429/5xx/timeout、usage/账单、模型映射仍
   UNVERIFIED；OpenCode Go 的 `x-opencode-session` 缺口需 PR5 smoke。
5. **LiveGate 与总体判定**：本 PR 不改变 `BLOCKED`/`DECISION PENDING`；不签发任何批准。

## 9. 证据

| 项 | 值 |
|---|---|
| 镜像 | `localhost/autoteacher-local-oci@sha256:62d3569ec38e27ed16fa3147515c1c78d993bb7df831cc1fe29811f3fe64667b`（id `56db1e2ad5ab…`） |
| 测试命令 | `artifacts/m0-controller-no-key/argv/no-key-tests.argv.json` |
| 时间/exit | `start-utc.txt` / `finished-utc.txt` / `exit-code.txt`（exit 0） |
| 计数 | 104 passed, 1 skipped（105 collected；unit/security 99 + integration 6） |
| 日志 | `artifacts/m0-controller-no-key/logs/`（stdout/stderr/collect/ruff） |
| 容器 absence | `container-absence-after.txt`（无匹配容器） |
| 产物 hash | `manifest.json` + `evidence.sha256`（`cd artifacts/m0-controller-no-key && sha256sum -c evidence.sha256`） |
| 代码 | `src/autoteacher_m0/security/{authorization,ed25519,credential_boundary,watchdog,live_controller}.py` |
| 测试 | `tests/unit/security/test_{authorization,credential_boundary,watchdog}.py`、`tests/integration/sandbox/test_live_controller_no_key.py` |

完成 PR3 **不代表** Live 已批准；任何真实 Key 注入、Provider 调用、E1–E5 Live 仍须
PR2/PR4 完成 + 维护者独立审批（v0.5 §PR5）。
