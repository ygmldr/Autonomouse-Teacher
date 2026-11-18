# M0 G4-C — Trusted Synthetic Egress 契约（冻结草案）

- **任务**：G4-C-01..18（`docs/Autonomous_Teacher_M0_G4_PreLive_NoKey_Agent_Execution_Plan_v1.0.md` §6；矩阵 `docs/Autonomous_Teacher_M0_G4_PreLive_Test_Evidence_Matrix_v1.0.csv`）
- **基线**：`795c263c06de1a4bbfde9392a6b32f3ab4f489be`（G4-A/B 完成，工作区 clean）
- **性质**：**no-key / no-model / no-network / no-live**。本契约只覆盖 **synthetic fixture route**；real provider route 在本轮 **BLOCKED**，不得因本文件存在而推断可联网。
- **状态**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING` 不变。
- **本文件不是**授权、不是 G4 PASS、不是 E5-PreLive Full。

---

## 0. 范围与不变量

G4-C 在既有 G3-C/G3-D 的 `PreparedProviderRequest` → Broker `Reserve`/`Claim` →
`ATTEMPT_STARTED` → Fake Provider 链路上增加两个**新增、可审计、默认关闭**的契约：

1. `ProviderRouteContract`：把「这条 route 到底允许发什么」从散落的 policy 常量固化为
   一份可序列化、可逐字段比较的冻结描述；synthetic fixture 与未来 real route **分开声明**。
2. `TrustedSendAuthorization`：由可信域在发送前一刻签发、绑定 Prepared/Payload/Claim/
   Attempt/Route/epoch/expiry 的一次性发送凭据；Candidate 无法提供、无法伪造、无法复用。

同时把 G4-A 提供的 `binding_drift("pre_dispatch", …)` 检查点**接线到真实发送前**。

**不变量（本契约冻结）**：

| 编号 | 不变量 |
|---|---|
| I1 | 任何 Provider 调用必须经过 `TrustedEgressTransport.dispatch()`；G4-C 门开启时还必须持有本进程签发且未消费的 `TrustedSendAuthorization`。 |
| I2 | `TrustedSendAuthorization` 只能由 `TrustedSendGate.authorize()` 在内存中签发；**不存在** `from_json`/`parse`/`load` 入口，任何 JSON mapping 都不是凭据。 |
| I3 | 授权绑定 `prepared_digest`、`payload_digest`、`payload_length`、`scope/run/call_id/reservation/claim/attempt/route/model/epoch/expiry`；发送前重新计算实际字节 SHA，绝不信任 Candidate 提供的摘要。 |
| I4 | 授权一次性：`consume()` 按对象身份从进程内注册表移除；重放、复制、跨 boundary 的授权一律拒绝。 |
| I5 | 发送前若 route contract、工具 schema、预算、绑定检查任一失败 → **Fake Provider 不被调用**（Fake 计数不变），账本保守（`ATTEMPT_STARTED` 之后失败记 `SETTLEMENT_UNCERTAIN`，永不 FREE）。 |
| I6 | 不自动重试：429/5xx/timeout/disconnect/EOF/无 Usage/部分 Usage 都是终态失败或保守 unknown，transport 只调用 provider 一次。 |
| I7 | 本轮只允许 `route_kind=synthetic_fixture` 且 `activation=ACTIVE_SYNTHETIC_ONLY` 的 route 通过；real route 模板恒 `BLOCKED_REQUIRES_HUMAN_VERIFICATION`。 |
| I8 | 不新开真实 socket/TLS/HTTP；`--network none`；Provider 是容器内 Fake 子进程（stdio）。 |
| I9 | 本契约不改变 G3-C/G3-D 协议、账本状态机或历史证据；门关闭时行为与 `795c263` 完全一致。 |

---

## 1. `ProviderRouteContract`

### 1.1 字段（冻结）

| 字段 | 类型 | 语义 |
|---|---|---|
| `route_id` | str | 内部 route 标识，必须与 Broker/Admission 的 route 完全一致 |
| `provider` | str | provider 名（synthetic 时与 route_id 同值） |
| `model_id` | str | 模型标识（synthetic fixture：`fixture-bridge-v1`） |
| `endpoint_host` | str \| None | 精确 host（**不是** suffix/通配）；blocked 模板为 None |
| `port` | int \| None | 精确端口；blocked 模板为 None |
| `method` | str \| None | 精确 HTTP 方法（synthetic：`POST`） |
| `exact_path` | str \| None | **精确路径**（不是前缀）；构造时拒绝 `..`/反斜杠/%2e/控制字符 |
| `request_format_version` | str \| None | 出站 payload schema 版本（synthetic：`m0.g3b.fake.v1`） |
| `streaming_contract` | str \| None | 流式帧契约名（synthetic：`synthetic_frames_v1`）；`none` 表示非流式 |
| `tokenizer_price_source_version` | str \| None | tokenizer/价格来源版本（synthetic：`fixture_synthetic_rate:v1`） |
| `max_output_tokens` | int | 单次输出硬上限（1..1024，与既有 `MAX_OUTPUT_TOKENS` 一致） |
| `allowed_tool_schema_digests` | frozenset[str] | 允许的 tool schema **canonical JSON SHA-256** 集合；空集表示禁止任何 tools |
| `retry_policy` | str | 只允许 `no_retry`（本契约无自动重试） |
| `allow_files` / `allow_images` / `allow_store` | bool | 三个独立开关，默认 False |
| `route_kind` | str | `synthetic_fixture` \| `real_provider` |
| `price_source` | str | synthetic：`fixture_synthetic_rate:v1`；real：`REQUIRES_VERIFICATION` |
| `activation` | str | `ACTIVE_SYNTHETIC_ONLY` \| `BLOCKED_REQUIRES_HUMAN_VERIFICATION` |

### 1.2 冻结实例

**Synthetic（唯一 ACTIVE）**：`SYNTHETIC_ROUTE_CONTRACT`

```text
route_id=offline-test-only-g3b        provider=offline-test-only-g3b
model_id=fixture-bridge-v1            host=g3b-fake.local  port=9000
method=POST  exact_path=/v1/g3b/chat
request_format_version=m0.g3b.fake.v1
streaming_contract=synthetic_frames_v1
tokenizer_price_source_version=fixture_synthetic_rate:v1
max_output_tokens=1024               retry_policy=no_retry
allowed_tool_schema_digests={skill_lookup canonical schema sha256}
allow_files=false allow_images=false allow_store=false
route_kind=synthetic_fixture          price_source=fixture_synthetic_rate:v1
activation=ACTIVE_SYNTHETIC_ONLY
```

> 说明：G3-B/G3-C/G3-D 的 `ROUTE="offline-test-only-g3b"` 同时用于 payload 的
> `provider` 字段与 `EgressRequest.route_id`。G4-C **不改变**该冻结协议值，因此
> contract 的 `route_id` 与 `provider` 取同一字符串；`TrustedSendGate` 仍分别逐字段
> 比较 `prepared.route_id` / `prepared.provider` / `model`，再与 Broker Claim 的
> reservation 绑定。两个字段都不是可联网 URL，任何 host/port 变更都会 fail-closed。
>
> `skill_lookup` 的 canonical schema 摘要取自已冻结的
> `artifacts/g3d/stage-20261117T221955Z/candidate/fixtures/capture-tools.json`
> （`c984bef0ae31771d…` 全值见 `artifacts/g4/c/stage-summary.json`），G4-C 启动时
> 会与 stage fixture 重新计算比对；不一致即 fail-closed。

**Real（BLOCKED 模板）**：`REAL_ROUTE_TEMPLATE`

```text
route_id=deepseek-official            provider=deepseek
model_id=None 端点/路径/版本/流式/tokenizer 全部 None
route_kind=real_provider              price_source=REQUIRES_VERIFICATION
activation=BLOCKED_REQUIRES_HUMAN_VERIFICATION
```

`send_problems()` 对 real route 恒返回
`REAL_ROUTE_BLOCKED_REQUIRES_HUMAN_VERIFICATION` + `PRICING_SOURCE_UNVERIFIED`。
真实 DeepSeek 的 model id、URL、header、Usage、计费、错误码必须在 G5 当天取官方资料并由
维护者审批（G4 §6.4）；本文件不硬编码任何旧 OpenCode Go 路由。

### 1.3 校验规则

- 所有字符串必须非空（blocked 模板的 None 字段除外）、无首尾空白、无控制字符；
- `method` 只允许 `POST`；`exact_path` 必须以 `/` 开头且满足上述路径拒绝表；
- `max_output_tokens` 必须是严格 int（拒绝 bool），1..1024；
- tool schema 摘要必须是 64 位小写 hex；
- `allow_*` 必须是严格 bool；
- `route_kind=synthetic_fixture` 且 `activation=ACTIVE_SYNTHETIC_ONLY` 时必须给出全部端点字段、
  `price_source` 必须是 `fixture_synthetic_rate:v1`；
- `route_kind=real_provider` 或 `activation=BLOCKED_…` 时端点字段**必须为 None**、价格源必须是
  `REQUIRES_VERIFICATION`，且 `send_problems()` 非空；
- 未知识别值/未知字段（`from_mapping`）→ 拒绝，不忽略。

---

## 2. `TrustedSendAuthorization`

### 2.1 绑定字段（冻结）

| 字段 | 来源 | 约束 |
|---|---|---|
| `schema_version` | 常量 | `m0.g4c.send-authorization.v1` |
| `authorization_id` | 可信域随机 nonce 派生 | `send-<32 hex>`，进程内唯一 |
| `scope_id` / `run_id` | Prepared（可信域构造） | 与 Admission/Prepared 一致 |
| `call_id` | 由 Prepared 摘要重算 | `call-[0-9a-f]{48}` |
| `prepared_digest` | `prepared_request_digest(prepared)` | 等于 Prepared 自带摘要、Broker Claim 摘要 |
| `payload_digest` | 实际出站字节 SHA-256 | 发送前重算；等于 Fake Receipt `raw_sha256` |
| `payload_length` | 实际出站字节长度 | 发送前重算 |
| `attempt_ordinal` | `EgressRequest.attempt_ordinal` | ≥1 |
| `reservation_id` | Broker Reserve 返回 | 与 Claim/Attempt 行一致 |
| `broker_claim_id` / `broker_claim_digest` | ClaimResult.claim | claim 内容摘要；`call_id/reservation/request_digest` 逐项复核 |
| `route_id` / `model_id` | contract + Prepared | 与两者一致 |
| `auth_epoch` | 本次 run 的可信 epoch | 跨 epoch 复用 → `AUTH_EPOCH_MISMATCH` |
| `issued_utc` / `expires_utc` | 可信时钟 | 默认有效期 30 s；过期 → `AUTHORIZATION_EXPIRED` |
| `route_kind` / `synthetic` | contract | 必须 `synthetic_fixture`/`True` |

### 2.2 生成与消费

```text
prepare(model) → PreparedProviderRequest(prepared_digest, call_id)
reserve → reservation_id
claim   → ClaimResult(claim.claimed=True, claim=<mapping>)
begin_attempt → ATTEMPT_STARTED(payload_digest, payload_length)
TrustedSendGate.authorize(prepared, request, permission, payload_bytes,
                          payload_digest, reservation_id, broker_claim_id…)
      ├─ route contract / schema / budget / pre_dispatch binding 检查
      ├─ 重算 prepared_digest、call_id、payload_digest、payload_length
      ├─ 复核 DispatchPermission 与 ClaimResult 的逐字段一致
      └─ 签发 authorization（进程内注册 + 审计 journal）
TrustedSendGate.consume(authorization, payload_bytes) → 重算字节 SHA、一次性移除
TrustedEgressTransport.dispatch(provider=…) → Fake Provider
```

- `authorize()` 任何失败 → 抛 `EgressViolation`，controller 在进入 transport **之前**
  转成 `EGRESS_DENIED`，Fake=0；
- `consume()` 任何失败 → provider 抛错，transport 记 `ATTEMPT_STARTED` + provider 异常，
  Fake=0；
- 审计 journal（`/work/state/g4c-send-journal.jsonl`，root 0600，append-only）记录
  `AUTHORIZED/CONSUMED/DENIED` 与全部绑定字段；journal 本身不是凭据。

### 2.3 禁止路径（逐项测试）

| 禁止路径 | 结果 |
|---|---|
| Candidate JSON 直接反序列化为授权 | 无 API；`consume(dict)` → `AUTHORIZATION_UNKNOWN` |
| 伪造/复制授权对象 | 注册表按 `id()` 复核 → `AUTHORIZATION_UNKNOWN` |
| 重放同一授权 | 第二次 `consume` → `AUTHORIZATION_REPLAYED` |
| 修改 payload 字节后发送 | `PAYLOAD_DIGEST_MISMATCH`，Fake=0 |
| 跨 run/epoch 使用授权 | `AUTH_EPOCH_MISMATCH` |
| 在 Claim 后修改 Prepared | `PREPARED_DIGEST_MISMATCH` / `PRE_DISPATCH_DENIED`，Fake=0 |
| 未 Claim 直接发送 | `DISPATCH_PERMISSION_REQUIRED`（transport 既有语义），Fake=0 |
| 已消费 Claim 再发 | Broker `ALREADY_CLAIMED`；无第二条发送路径 |

---

## 3. 预算与错误映射

### 3.1 预算（synthetic fixture）

| 阈值 | 值 | 行为 |
|---|---|---|
| `soft_total_usd` | 3.00 | 累计超过 → 发送继续但记 `soft_ceiling_exceeded`（**不是** FREE） |
| `hard_total_usd` | 10.00 | 累计（known + worst-case held）将超过 → 拒绝 `HARD_BUDGET_CEILING_EXCEEDED` |
| `soft_call_usd` | 0.10 | 单次超过 → 记录 soft 调用事件，仍允许 |
| `hard_call_usd` | 0.20 | 单次 `estimated_cost_usd` > 0.20 → 拒绝 `PER_CALL_BUDGET_EXCEEDED` |
| `max_sends` | 50 | 授权数达到上限 → `SEND_AUTHORIZATION_LIMIT_REACHED` |
| 输出 token | contract.max_output_tokens=1024 | 超过 → `MAX_TOKENS_EXCEEDED` |

成本来自 `EgressRequest.estimated_cost_usd`（Decimal 字符串）与 worst-case 上限；
**未知成本不得默认为 0**。synthetic 费率固定，不声称是供应商真实价格。

### 3.2 错误映射（无自动重试）

| Fake 场景 | 状态 | 发送次数 |
|---|---|---|
| 200 + 完整 usage | `SETTLED_USAGE` | 1 |
| 200 + 无/部分 usage | `BILLABLE_UNKNOWN`（worst-case held） | 1 |
| 429 / 4xx | `NOT_BILLABLE_HTTP_ERROR` | 1 |
| 5xx | `BILLABLE_UNKNOWN` | 1 |
| timeout / hang / disconnect / EOF | `BILLABLE_UNKNOWN` | 1 |
| 恶意重复 usage / 冲突 usage | 拒绝或保守 unknown，绝不 FREE | ≤1 |

---

## 4. `pre_dispatch` 与 G4-A 接线

G4-A `authorization.binding_drift(checkpoint, approved, observed)` 支持
`pre_start` / `pre_reserve` / `pre_dispatch`。G4-C 的接线：

1. **approved**：由可信 Launcher 在 stage 构建后写入 G4 专用
   `binding-approved.json`（15 组件闭包 → 5 个 root，见 G4-A §8）。它绑定 **G4-C 实现提交**
   的 `src/` blob、G3-B/G3-D 配置、锁文件、插件树、profile、预算与价格快照；
2. **observed**：可信容器内 `trusted_entry_g4c.py` 在启动与**每次发送前**重新计算：
   - 容器内可见 `/project/src/**`、`/project/fake/**` 文件 → 逐文件 SHA；
   - 未挂载进容器的仓库/构建输入（config/plugins/pyproject/uv.lock）→ 由 Launcher 在启动前
     从工作树重算并以 `declared` 形式传入（root 0400，Candidate 不可挂载）；
   - `candidate_stage`/`runtime_binary`/`runtime_dependencies` → 由 stage manifest /
     REFERENCE.json 的 canonical 树哈希代表；
3. `authorize()` 调用前执行 `binding_drift("pre_dispatch", approved, observed)`，
   任何 `<ROOT>_MISMATCH` → `PRE_DISPATCH_BINDING_DRIFT:<ROOT>_MISMATCH`，Fake=0；
4. 若 approved 或 observer 缺失 → `PRE_DISPATCH_CHECK_INCOMPLETE`（fail-closed，不允许
   “没配置就跳过”）；
5. 若 observer 抛错 → `PRE_DISPATCH_CHECK_ERROR`（fail-closed）。

**组件摘要配方（G4-C）**：

```text
component_digest = sha256( canonical_json( sorted([[relpath, sha256(file_bytes)], ...]) ) )
root             = ExpectedBindings.from_closure({15 components})   # G4-A 原语义
```

容器内能读到的 `/project/src/**`、`/project/fake/**` 文件逐字节复算；其余文件使用
Launcher 传入的 `declared` sha（同配方参与摘要），`candidate_stage`/`runtime_binary`/
`runtime_dependencies` 以 canonical `EXTERNAL.json` 清单（含树/二进制的原始 canonical
哈希）表示。Launcher 在启动前从**工作树与 stage manifest**独立计算 `approved`，
trusted 容器启动时重算 `observed` 并执行 `binding_drift("pre_start")`；每次发送前再执行
`binding_drift("pre_dispatch")`。

**证据等级限制**：容器内只有 `/project` 的 ro 挂载，`config/`、`plugins/`、`pyproject.toml`
不在容器内，因此这些组件只能由 Launcher 侧重算并声明；容器侧能独立复算的是代码面
（`src/**`、`fake/**`）。本文件**不声称**在容器内复算全部 15 组件。部署侧 OS 级不可变
（root 只读挂载 / 独立信任域）仍属 G4-H。

---

## 5. G4 专用 Stage / Launcher 偏差说明（必须保留）

G3-D 的冻结 launcher `scripts/g3d/launch.py` 在 preflight 中执行：

```text
git diff --quiet 4bd4803 -- src
git diff --quiet <PRODUCT_BASE> -- spikes plugins
```

G4-A 已按授权修改 `src/autoteacher_m0/security/{authorization,ed25519,live_controller}.py`
（提交 `382b4ee`），G4-C 还会修改 `security/egress.py` 与 `bridge/controller.py`，因此
`git diff cf40c6b -- src` **必然非空**，冻结 launcher 会以
`src_differs_from_base` 拒绝运行。**不修改 `scripts/g3d/**`，不修改历史测试/证据**。

G4-C 的处理：

1. 新增 `scripts/g4/build_stage_c.py`：调用 G3-D 的 `build_stage(base=G4_IMPL_SHA)`，
   在**内存中**把 `lib_g3d.PRODUCT_BASE` 重绑定为 G4 实现提交（不修改文件），
   使 stage manifest 的 `base_sha`/`head_at_build` 指向 G4 提交；产物落在
   `artifacts/g4/c/stages/`，**不写** `artifacts/g3d/commands.jsonl`；
2. 新增 `scripts/g4/launch_c.py`：G4 专用 launcher，复用 `lib_g3d` 的 run layout、
   UID/mount/`--network none` 参数、socket/peercred/identity 采集与清理辅助，但：
   - preflight 的 base 改为 G4 实现提交，并校验 stage 与 G4 manifest；
   - trusted 容器入口改为 `/g4c/trusted_entry.py`（`run_dir/g4c-run` 的 ro 挂载），
     不修改 stage 内冻结的 `trusted_entry.py`；
   - `controller.py` 只增加可选 `dispatch_gate` 参数与调用点；默认 `None` 时
     G3-C/G3-D 行为逐字节不变；
3. G3-D 冻结证据（`artifacts/g3d/**`、`docs/M0_G3D_*`、G3 矩阵）**不改**；
4. 举证时区分：`G3-D 冻结 launcher 证据不变` 与 `G4-C G4 专用 launcher 证据`，
   不得把后者冒充前者。

---

## 6. 测试与证据约定（C01..C18）

| Case | 场景 | 层级 | 关键断言 |
|---|---|---|---|
| C01 | 真实 DSH Echo 一次发送 | L2 容器 | 1 Reserve/Claim/Attempt/Receipt/Settlement；Fake=1；DSH usage==receipt；0 live |
| C02 | 真实 DSH Tool 两轮 | L2 容器 | 2 套独立账本；Fake=2；skill_lookup 结果进入第二请求；两对 Digest |
| C03 | 无 Claim/伪造/已消费 Claim | L1-HOST + L2 重复身份 | Fake=0；无未授权 Attempt |
| C04 | Claim 后改 Prepared | L1-HOST（gate + controller helper） | Fake=0；`PREPARED_DIGEST_MISMATCH` |
| C05 | 发送前改 wire 字节 | L1-HOST（gate + transport spy） | Fake=0；`PAYLOAD_DIGEST_MISMATCH` |
| C06 | route/host/path/verb/model/tool schema 篡改 | L1-HOST + L2 raw-UDS | fail-closed；Fake=0 |
| C07 | ATTEMPT 后、发送前 crash | L2 容器（`G3B_CRASH_HOOK`） | Attempt durable；重放不发送 |
| C08 | Fake 收到后、结算前 crash | L2 容器 | Receipt 一次；保守 hold；重放不发送 |
| C09 | Broker stop/hang/timeout | L2 容器 | 有界失败；Fake=0；reservation 保守 |
| C10 | synthetic 429/5xx/timeout/eof | L1-HOST（Mock/Fake 场景） | 无 success finish；无自动重试 |
| C11 | missing/partial/duplicate/conflicting usage | L1-HOST | 不 FREE、不假成功 |
| C12 | 同业务身份 replay | L1-HOST + L2 容器 | 至多一次 Fake |
| C13 | direct HTTP/fallback/网络旁路 | L2 容器网络探针 + 静态扫描 | 0 外连；无第二条发送路径 |
| C14 | 预算软/硬阈值 | L1-HOST（gate budget） | soft 记录、hard 拒绝 |
| C15 | 未知 pricing / real route | L1-HOST + 静态 | real BLOCKED；synthetic 标注 |
| C16 | Session resume 不重发 | L1-HOST + 引用 L2 | 旧 Attempt 不重发；usage 一致 |
| C17 | Prepared vs Payload 两对 Digest | L1-HOST + L2 C01/C02 | Prepared=claim；Payload=receipt；两值分别校验 |
| C18 | 流式首帧早于 Fake 退出 | L2 `stream` 场景 | 同宿主时钟 `first_chunk_flushed` < `exit_after_finish` |

**强制声明**：`provider_route_kind=synthetic_only`、`real_model_calls=0`、
`real_external_http_calls=0`、`provider_keys_seen=0`、`billable_send_allowed=0`、
`LiveGate.status=BLOCKED`。synthetic 证据不得写成 real route PASS。

---

## 7. 残余与未主张

| ID | 残余 |
|---|---|
| R1 | 容器内只能独立复算 `src/**`/`fake/**` 组件；config/plugins/lock 由 Launcher 声明（§4） |
| R2 | `pre_dispatch` 与 `transport.dispatch` 之间仍有 Python 内存窗口；缓解是 payload 字节 SHA 在 consume 时重算、Fake 只接受该字节 |
| R3 | 授权/审计 journal 位于 `/work/state`（root 0700），不是独立签名账本；OS 级不可变属 G4-H |
| R4 | G4-C 只在 synthetic fixture route 上验证；真实 route/TLS/DNS/redirect/代理风险未证明 |
| R5 | C04/C05/C10/C11/C14/C15 的可注入面无法由 Candidate 远程触发，只能用真实 Controller+Broker+Fake 的宿主集成测试（L1-HOST），不得冒充 L2 |
| R6 | G3-D 冻结断言 `test_runner_does_not_modify_product_src` 因 G4-A/C 授权改码必然失败（如实登记，不改历史测试） |
| R7 | 价格 3.00/10.00 是工程硬顶，不是供应商侧额度；synthetic 费率不是真实价格 |
| R8 | 本轮 0 真实 Key/模型/外网/Live；`LiveGate`、`run_live.sh` exit 3、CLI/Adapter 均未改 |

---

## 8. 冻结与变更控制

- 本文件是 G4-C 的**设计契约**，实现必须逐字段匹配；任何字段增删必须同步更新
  `src/autoteacher_m0/security/egress.py` 的 dataclass、测试与矩阵，并在 G4-E 冻结时
  记录 `docs_sha`/`impl_sha`。
- 本契约**不授权**：真实 Key、真实 Provider、真实 HTTP/TLS、Live、G4-D、G5、G6。
- **STOP**：G4-C 完成后不自动进入 G4-D。
