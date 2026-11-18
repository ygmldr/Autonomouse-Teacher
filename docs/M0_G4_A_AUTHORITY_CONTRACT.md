# M0 G4-A — 可信批准契约（无 Key 授权校验器）实现与证据

- **任务**：G4-A-01..15（`docs/Autonomous_Teacher_M0_G4_PreLive_NoKey_Agent_Execution_Plan_v1.0.md` §4；矩阵 `docs/Autonomous_Teacher_M0_G4_PreLive_Test_Evidence_Matrix_v1.0.csv`）
- **执行者**：G4-A Trusted Approval Contract Agent
- **基线**：`e3d270e2277087e0642dda8803111885d0dbad3f`（G4-00 完成、工作区 clean，起点已核实）
- **实现提交**：`382b4ee27eba3d31f17ca2c9cd36b1d6332c559c`，父 `76f2b18511c9dc577c299ec53dad1d870efbeb0a`。
  说明：`e3d270e` 之后有 4 个**并行 G4-B** 提交进入共享 HEAD（仅 `config/g4`、`scripts/g4`、`tests/integration/g4_b`），
  本包提交只包含 3 个 `src/autoteacher_m0/security/` 文件与 `tests/integration/g4_a/`，未包含也未改动 G4-B 路径；`git show --stat 382b4ee` 可复核。
- **本轮时间（UTC）**：2026-11-18T15:56Z → 16:46Z
- **性质**：**no-key / no-model / no-network / no-container-start**。0 真实 Key、0 模型调用、0 外部 HTTP/TCP、0 计费请求；未执行 `podman pull`；`podman ps -a` 全程为空；未启动容器。
- **本轮裁定**：**`PASS_NO_KEY_AUTH_VALIDATOR`**（限定于“离线授权校验器 + 失败关闭组合”范围）。
- **明确不声明**：**`HUMAN_AUTHORIZATION_DEPLOYED` 未达成**；本文件不是 Live 授权、不是 G4 PASS、不是 E5-PreLive Full。
- **状态不变**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING`。

---

## 0. 裁定摘要

| 项 | 结果 |
|---|---|
| 授权格式 | 复用既有 `at-m0/execution-authorization/v1` 与 `ExpectedBindings`，**未新建第二套格式**；5 个绑定字段语义不变 |
| 签名有效 ≠ 可发送 | `AuthorizationDecision.signature_valid=True` 与 `billable_send_authorized=False` 分列；`billable_send_authorized=True` 在构造时直接 `ValueError` |
| 合成签名 | `TEST_ONLY_` 合成 Ed25519 fixture 通过 verifier（`approved=True`），但 `LiveGate`/CLI/`run_live.sh`/Adapter 全部 BLOCKED/exit 3，真实发送 0 |
| Ed25519 负例 | 小阶、order-4/8、torsion/mixed-order、非 canonical 公钥与 R、`S>=L`、短/长签名、非 bytes 输入全部 `False`，无未捕获 traceback |
| Strict JSON | 重复 key（顶层与嵌套）、NaN/±Infinity、bool-as-int、float-as-int、unknown fields、未知 route/model、工具白名单变化、过期/未生效/零 skew、撤销、重放逐条拒绝 |
| 可信文件边界 | Approval/Keys/Revocations 必须仓库外、目录私有（非 group/other 可写、非 candidate uid）、非 symlink、常规文件；`O_NOFOLLOW` + `fstat` 复核；候选 Stage 内放置由 Controller 拒绝 |
| SHA 绑定闭包 | 15 个运行时输入组件 → 5 个 v1 聚合根；组件缺失/多余/替换均拒绝；任一组件漂移使对应根变化并 deny |
| TOCTOU | 定义并测试 `pre_start` / `pre_reserve` / `pre_dispatch` 三个检查点；Reserve 侧消费函数**重跑全量校验**后才落一条单次使用记录 |
| 预算权威源 | **代码常量即冻结契约**（soft 3 / hard 10 / soft-call 0.10 / hard-call 0.20 / 50），经 `code_sha256` 绑定；`config/budgets.yaml` 为**声明镜像**，严格解析 + 逐字段漂移检测；pricing `REQUIRED_UNVERIFIED` 恒上报 |
| 重放/epoch | 一个 authorization_id **全局单次消费**；同 epoch 复用 → `AUTHORIZATION_REPLAYED`；跨 run/epoch → `AUTHORIZATION_EPOCH_MISMATCH`；新 run 必须新签名 ID；无无限复用许可 |
| 测试 | `tests/integration/g4_a/`：**223 passed / 0 failed，exit 0**（97.87s）；必跑回归：**404 passed, 1 deselected（exit 0）**；含冻结 G3-D 基线断言时 **1 failed, 404 passed（405 collected，exit 1，已归因）** |
| ruff | `authorization.py`、`ed25519.py`、`live_controller.py` + `tests/integration/g4_a/`：**All checks passed**（pinned 0.17.5） |
| 真实计数 | `real_provider_calls=0`、`real_external_http_calls=0`、`provider_keys_seen=0`、`billable_send_allowed=0`、`live_gate=BLOCKED`、`run_live_exit=3` |

---

## 1. 范围、基线与“未改动”清单

### 1.1 起点核实

- `git rev-parse HEAD` = `e3d270e2277087e0642dda8803111885d0dbad3f`（与任务书期望一致）。
- 起点 `git status --porcelain=v1 -uall` = 0 行。
- 本轮**未重写**任何 G3-C/G3-D 证据、测试、矩阵历史行；仅新增 `tests/integration/g4_a/`、本文件与 G4-A 矩阵行。

### 1.2 产品代码改动（3 个文件，最小增量）

| 文件 | 增量内容 |
|---|---|
| `src/autoteacher_m0/security/authorization.py` | 可信文件读取加固；`signature_valid`/`billable_send_authorized`；15→5 绑定闭包与 `binding_drift`；`checkpoint` 参数；`AUTHORIZATION_EXPIRED`/`AUTHORIZATION_NOT_YET_VALID`；预算镜像严格解析与漂移；单次消费记录 `consume_execution_authorization` |
| `src/autoteacher_m0/security/ed25519.py` | 仅 `verify`/`is_valid_public_key` 的输入归一化与 `TypeError` 捕获（非 bytes、错误长度、畸形点一律返回 `False`，不抛 traceback）；签名数学未改 |
| `src/autoteacher_m0/security/live_controller.py` | inspect-only 组合：预算常量补 soft 两项；预算镜像漂移、route 冻结白名单、可信文件位于候选 Stage 三类原因；`binding_checkpoint`；透传 `observed` 与两个布尔字段；**仍无 `run()/dispatch()/send()`** |

### 1.3 明确未改动（硬约束）

- `src/autoteacher_m0/security/gates.py`：**未改**（`LiveGate` 仍恒 BLOCKED）。
- `scripts/run_live.sh`：**未改**（仍 `exit 3`）。
- `src/autoteacher_m0/runtime/dsh_adapter.py`：**未改**（4 个 live 入口仍先 `_require_live_authorization()`）。
- `src/autoteacher_m0/cli.py`：**未改**（`--live` 仍先 `LiveGate().require_live()`）。
- `src/autoteacher_m0/security/__init__.py`：**未改**（不在本包写域）；新增 API 由 `autoteacher_m0.security.authorization` 直接导入，见 §15-R4。
- DSH 核心、其他 agent 文件、历史证据：**未改**。

---

## 2. 信任根与人类职责分界

1. **真实信任根不存在**：本轮没有独立部署的人类审批公钥、撤销服务、凭据 broker 或 egress proxy；`ALWAYS_BLOCKED_REASONS` 的 5 条事实基础不变。
2. **仅合成 fixture**：所有签名使用 `tests/integration/g4_a/g4a_support.py` 中的 `TEST_ONLY_` 种子（`5a…`），**仅存在于测试进程内存**；测试结束即消失。种子/私钥不写入仓库、Stage、Packet、决策对象或日志。
3. **`ed25519.sign()` 仅测试离线调用**：生产 `src/` 中 `ed25519` 的唯一使用点是 `authorization.py` 的 `verify`/`is_valid_public_key`（A15 AST 扫描断言）；无 seed 字段、无签名 API 可达路径。
4. **批准三文件必须来自仓库外**：`authorization`、`trusted-keys`、`revocations` 均按 §5 的边界读取；仓库内文件、symlink、group/other 可写、candidate uid 拥有、非常规文件、不可读、超大/空文件一律 `EXTERNAL_AUTHORIZATION_INVALID`。
5. **人类职责**（G4-H，未执行）：创建/保护真实公钥与撤销文件、离线保管私钥、定义轮换/吊销、审批精确冻结清单、部署只读挂载。Agent 不得代签、不得写 “APPROVED” 代替授权。

---

## 3. 授权判定语义：三个布尔字段必须分列

```text
signature_valid           Ed25519 签名在 pinned key 下对 canonical payload 验证通过
approved                  整份离线文档通过全部策略检查（仅是“准入诊断”）
billable_send_authorized  本模块恒为 False（构造 True 直接 ValueError）
```

- 合法合成签名：`approved=True, signature_valid=True, billable_send_authorized=False`（A01）。
- 时间过期但签名有效：`approved=False, signature_valid=True`（A08 明确断言）。
- `TrustedLiveController.inspect()` 同时返回 `authorization_approved`、`signature_valid`、`billable_send_authorized`，且 `status` 恒 `BLOCKED`、`boundary_deployed=False`。
- `LiveGate`、CLI `--live`、`scripts/run_live.sh`、`HarnessAdapter._require_live_authorization()` 的行为负例与上述字段**互相独立**：A01 同时验证 4 条入口。

**证据**：`tests/integration/g4_a/test_a01_signature_vs_billable.py`（5 tests）。

---

## 4. 授权格式复用（不新建第二套）

- 文档 schema：`at-m0/execution-authorization/v1`；字段集合保持既有 14 个顶层键（含 `approval_note`、`signature`）。
- 绑定：沿用 `ExpectedBindings` 的 5 个字段（`code/lock/runtime/plugin/merged_profile`）。
- 复用既有：`approved_route`、`allowed_tools`、`budget`、`deadline`、`key_id`、`revocation`、时间窗（`issued/not_before/expires`）。
- 新增能力全部是**校验器内部函数**，不改变签名文档格式：
  - `ExpectedBindings.from_closure()` / `closure_digests()`：把 15 个组件聚合为既有 5 个根；
  - `binding_drift(checkpoint, approved, observed)`：检查点比较；
  - `parse_budget_policy()` / `budget_policy_drift_reasons()`：预算镜像校验；
  - `consume_execution_authorization()`：Reserve 侧单次消费。
- `TrustedLiveController` 保持 **inspect-only**，无 `run()`（A01 断言不存在 `run/dispatch/send/execute/approve/sign`）。

---

## 5. 可信文件边界（Approval / Keys / Revocations）

每次读取（load 与 consume 均重跑）执行：

| 检查 | 失败结果 |
|---|---|
| 路径必须绝对路径 | `EXTERNAL_AUTHORIZATION_INVALID:<detail>` |
| 最后一段不得是 symlink；打开时 `O_NOFOLLOW` | 同上 |
| 目录必须存在、解析后位于仓库外 | 同上 |
| 目录不得 group/other 可写，owner 不得为 candidate uid `65534` | 同上 |
| `os.fstat` 必须是常规文件、mode 不得 group/other 可写、owner 不得为 candidate | 同上 |
| 大小 `0 < size <= 上限`（authorization 64 KiB / keys 16 KiB / revocations 64 KiB） | 同上 |
| 读后字节数必须等于 fstat 大小 | 同上（防读取期间替换） |
| 解析：UTF-8、JSON object、无重复 key、无 NaN/Infinity、非 Markdown | 同上 |

- **候选 Stage 排除**由 Controller 组合层完成：三个文件若位于 `candidate_stage` 内 → `TRUSTED_APPROVAL/KEYS/REVOCATION_PATH_INSIDE_CANDIDATE_STAGE`，`status=BLOCKED`。单独调用 `load_execution_authorization` 无法知道 Stage 路径（见 §15-R5）。
- **残余窗口**：检查目录与 `os.open` 之间仍存在父目录被同 owner 替换的窗口；部署要求是 root 所有、只读挂载的受保护目录（G4-H）。本轮已消除“最后一段 symlink 交换”和“读取期间换文件”两类。

**证据**：`test_a07_trusted_file_boundary.py`（12 tests）、`test_a14_key_registration_rotation.py`（18 tests）。

---

## 6. Ed25519 负例矩阵（P0）

| 类别 | 构造 | 结果 |
|---|---|---|
| 小阶公钥 | identity `01…00`、`00…00`、`00…80`、order-4、order-8（`c717…037a/03fa`、`26e8…fc05/fc85`） | `is_valid_public_key=False`；keys 文件 → `EXTERNAL_AUTHORIZATION_INVALID` |
| identity 伪造 | `A=identity, R=B, S=1`（方程成立） | 仍拒绝（严格入组检查） |
| torsion / mixed-order | `A = B + T8` | 非 prime-order；`verify=False`；keys 拒绝 |
| 非 canonical 公钥 | `y = Q+1`、`y=1` 带 sign bit（x 恢复为 Q） | `_decode_point` `ValueError`；`False` |
| R 非 prime order | R=identity / order-8 / mixed-order / 非 canonical | `verify=False` |
| S 越界 | `S=0,1,L-1,L,L+1,2^256-1` | `False`（`S>=L` 直接拒绝） |
| 短/长签名 | 0/1/31/32/63/65/96/128 字节 | `False` |
| 非法公钥长度 | 0/1/31/33/64/96 字节 | `False` |
| 非 bytes 输入 | `None/int/float/object/str` | `False`，**无 traceback**（`isinstance` 前置 + 窄捕获 `ValueError/TypeError`） |
| bytes-like | `bytearray`/`memoryview` | 正常归一化并通过（合法签名 True） |
| 授权层 | 大写 hex、非 hex、63 字节、`0*64`、`algorithm=rsa`、篡改 payload | `SIGNATURE_ENCODING_INVALID` / `SIGNATURE_ALGORITHM_NOT_APPROVED` / `HUMAN_SIGNATURE_INVALID` |

**证据**：`test_a02_small_order.py`（9）、`test_a03_torsion_noncanonical.py`（8）、`test_a04_signature_lengths.py`（29）。

---

## 7. Authorization JSON 严格解析

| 输入 | 稳定错误码 |
|---|---|
| 重复 key（顶层/`budget`/`signature` 等嵌套） | `EXTERNAL_AUTHORIZATION_INVALID:...duplicate key` |
| `NaN` / `Infinity` / `-Infinity` | `EXTERNAL_AUTHORIZATION_INVALID:invalid ...` |
| 根不是 object、Markdown、BOM、UTF-16、尾随垃圾、空文件、>64 KiB | `EXTERNAL_AUTHORIZATION_INVALID` |
| 缺字段 / 多字段（含 `approved`、`user_approval`、`agent_self_approval`） | `AUTHORIZATION_SCHEMA_FIELDS_INVALID` |
| `schema` 非 v1 | `AUTHORIZATION_SCHEMA_UNKNOWN` |
| `authorization_id` 非 `[A-Za-z0-9._:-]{1,128}` | `AUTHORIZATION_ID_INVALID` |
| `approver` 空/非字符串；`approval_note>2000` | `APPROVER_INVALID` / `APPROVAL_NOTE_INVALID` |
| `bindings` 字段集合/摘要格式错 | `BINDING_FIELDS_INVALID` / `BINDING_DIGESTS_INVALID` |
| route 未知字段/类型错 | `ROUTE_FIELDS_INVALID` |
| route/model/provider 与受信期望不同（未知 route/model） | `ROUTE_NOT_APPROVED` |
| `allowed_tools` 类型错/重复/含 `shell`/空 | `ALLOWED_TOOLS_INVALID` / `ALLOWED_TOOLS_NOT_PERMITTED` |
| 实际工具注册表与授权不同 | `ACTUAL_TOOL_REGISTRY_NOT_APPROVED` |
| budget/deadline 未知字段/类型错 | `BUDGET_FIELDS_INVALID` / `DEADLINE_FIELDS_INVALID` |
| `max_calls`/`total_seconds`/`max_steps` 为 bool、float、string、null、list、object | `BUDGET_VALUES_INVALID` / `DEADLINE_VALUES_INVALID` |
| USD 为 JSON number、bool、指数、带空格/符号、0、7 位小数 | `BUDGET_VALUES_INVALID` |
| 范围越界 | `MAX_CALLS_OUT_OF_RANGE` / `PER_CALL_CAP_EXCEEDS_TOTAL_CAP` / `TOTAL_CAP_EXCEEDS_HARD_BUDGET` / `DEADLINE_OUT_OF_RANGE` |
| 时间窗非法/超 24h/签发超过 7 天/格式错 | `AUTHORIZATION_TIME_WINDOW_INVALID` / `AUTHORIZATION_LIFETIME_TOO_LONG` / `AUTHORIZATION_TOO_OLD` / `AUTHORIZATION_TIME_INVALID` |
| 过期 / 未生效 / 任意方向 clock skew | `AUTHORIZATION_NOT_CURRENT` + `AUTHORIZATION_EXPIRED` / `AUTHORIZATION_NOT_YET_VALID`（**零 skew 容忍**，`not_before` 含边界、`expires` 不含） |
| authorization_id 在撤销列表 | `AUTHORIZATION_REVOKED` |
| 重复消费 / 跨 epoch | `AUTHORIZATION_REPLAYED` / `AUTHORIZATION_EPOCH_MISMATCH` |

所有拒绝路径均 `approved=False`、`billable_send_authorized=False`，且**不产生 use 记录**（不进入任何 dispatch）。

**证据**：`test_a05_strict_json.py`（20）、`test_a06_integer_types.py`（32）、`test_a08_time_expiry_revocation.py`（17）、`test_a10_route_tools_budget.py`（21）。

---

## 8. SHA 绑定闭包（15 组件 → 5 个既有根）

### 8.1 组件与聚合根

| 组件 | 生产输入 | 根 |
|---|---|---|
| `trusted_controller` | `bridge/{controller,ipc_server,admission,attempts,protocol,broker_client}.py` | `code_sha256` |
| `trusted_broker` | `accounting/{broker,broker_usage,budget,call_identity,ledger,observation,pricing,usage}.py` | `code_sha256` |
| `egress_boundary` | `security/egress.py` + `config/dsh/target-broker-policy.json` | `code_sha256` |
| `candidate_adapter` | `runtime/dsh_adapter.py` + `cli.py` | `code_sha256` |
| `security_primitives` | 7 个 `security/*.py`（含 `authorization`/`ed25519`/`gates`/`live_controller`/`credential_boundary`/`watchdog`/`__init__`） | `code_sha256` |
| `dependency_lock` | `pyproject.toml` + `uv.lock` | `lock_sha256` |
| `runtime_dependencies` | deps canonical（G4-00 `e07729d7…`；fixture 为 TEST_ONLY 占位） | `lock_sha256` |
| `runtime_binary` | DSH runtime canonical（G4-00 `1cc41d5a…`；fixture 占位） | `runtime_sha256` |
| `candidate_stage` | Stage canonical/manifest（G4-00 `e1ff1449…`/`644823d4…`；fixture 占位） | `runtime_sha256` |
| `plugin_tree` | `plugins/{offline-fixture,runtime-budget-guard,skill-lookup}` 运行相关 14 文件 | `plugin_sha256` |
| `tool_registry_schema` | `config/dsh/target-runtime.patch.yml` | `plugin_sha256` |
| `merged_profile` | `config/dsh/{sdk-minimal,target-runtime,target-runtime-opencode-go}.patch.yml` | `merged_profile_sha256` |
| `route_policy` | `src/autoteacher_m0/settings.py` + `config/dsh/target-runtime-opencode-go.patch.yml` | `merged_profile_sha256` |
| `budget_policy` | `config/budgets.yaml` | `merged_profile_sha256` |
| `price_snapshot` | `config/models.example.yaml` + `live_pricing_snapshot` | `merged_profile_sha256` |

### 8.2 规则

```text
component_digest = sha256( canonical_json( [[rel_path, sha256(bytes)], ...] 按 path 排序 ) )
root_digest      = sha256( canonical_json( {component: component_digest for component in group} ) )
```

- 组件必须与 `BINDING_COMPONENTS` **完全一致**：缺失或额外组件 → `ValueError`（候选不能自选不完整清单）。
- 任一组件变化 → 恰好其所属根变化 → 新 dispatch 的比较得到 `<ROOT>_MISMATCH`（A09 对 15 个组件逐一断言“恰好一个根变化”）。
- v1 文档仍只含 5 个字段；这是**解释层**扩展，不是第二套授权格式。G4-B 将冻结权威 manifest（本文件的组件路径表是 G4-A 契约声明，非独立构建产物，见 §15-R3）。
- 验收正例：以闭包根签名 → `approved=True`；伪造/漂移根 → 拒绝。

### 8.3 TOCTOU 检查点与窗口

| 检查点 | 调用 | 语义 |
|---|---|---|
| `pre_start` | `load_execution_authorization(..., observed=...)` / `TrustedLiveController.inspect(observed=...)` | 启动前独立重算闭包；漂移 → `BINDING_DRIFT:PRE_START:<ROOT>_MISMATCH` |
| `pre_reserve` | `consume_execution_authorization(...)` | **重跑全量校验**（三文件、pinned keys、撤销、时间、绑定、observed）→ 通过才用 `O_CREAT|O_EXCL|O_NOFOLLOW` 落一条单次使用记录 |
| `pre_dispatch` | `binding_drift("pre_dispatch", approved, observed)` | 每次真实发送前必须再比较；本轮无发送路径，G4-C 必须接线 |

窗口解释：

- 三个检查点之间仍可能有时间间隔；本轮的处置是“**检查点之后任何变化都使下一次检查 deny**”，且**没有**任何发送实现，故不存在“检查后发送”的代码窗口。
- G4-C 落地时，`pre_dispatch` 必须紧邻 `PreparedProviderRequest` 摘要校验（G3-C 已有 `prepared_request_digest == BrokerClaim.request_digest`），使“检查 → 发送”之间的可修改面收敛到已绑定摘要的字节。
- 部署侧必须用 root 只读挂载消除同 owner 替换窗口；本模块无法在 Python 内证明这一点（§15-R7）。

**证据**：`test_a09_binding_closure.py`（6）、`test_a13_toctou_checkpoints.py`（13）。

---

## 9. 绕过负例（P0）

| 绕过 | 结果 |
|---|---|
| 仓库内 `SECURITY_APPROVALS.md` / `# APPROVED` Markdown | 拒绝（位于仓库内或非 JSON） |
| 外部目录中的 Markdown | `EXTERNAL_AUTHORIZATION_INVALID`（Markdown） |
| `--live`（`smoke`/`paired`，含 `--budget-usd`） | CLI exit **3**，JSON `status=BLOCKED,error_code=SECURITY_BLOCKED` |
| `scripts/run_live.sh` | exit **3**，stderr `BLOCKED SECURITY_BLOCKED` |
| `AT_M0_LIVE_APPROVED` / `AT_M0_ALLOW_LIVE` / `AT_M0_APPROVAL_MD` / `AT_M0_APPROVAL` | 对 verifier 与 CLI 均无效果；缺失授权文件仍拒绝 |
| 伪造用户批准字段（`approved/user_approval/human_approval`） | `AUTHORIZATION_SCHEMA_FIELDS_INVALID` |
| 自签测试签名（未注册密钥） | `HUMAN_SIGNATURE_INVALID` / `UNKNOWN_APPROVAL_KEY` |
| `assert_live_entrypoints_blocked` 文本审计 | **仅为辅助证据**：本测试显式演示其盲点（在 adapter 副本中追加一个函数后审计仍返回空）；真正的负例是行为测试（Gate/CLI/script/Adapter） |

**证据**：`test_a11_bypass_negatives.py`（6 tests）。

---

## 10. 预算权威源（修复 G4-00 发现的常量/配置脱节）

### 10.1 权威定义

- **权威源 = 冻结代码常量**（`live_controller.py`，经 `code_sha256` 闭包绑定）：
  - `soft_total_usd=3.00`、`hard_total_usd=10.00`
  - `soft_call_usd=0.10`、`hard_call_usd=0.20`
  - `max_live_requests=50`
- **`config/budgets.yaml` = 声明镜像**，位于 Agent 可写域，**不能**单独作为安全权威；任何改动必须与常量一致，否则显式 deny。
- 授权文档中的 `budget` 必须与 Controller 的冻结预算逐字段相等（`BUDGET_POLICY_MISMATCH:<field>`）。

### 10.2 漂移检测（不被静默忽略）

| 场景 | 错误码 |
|---|---|
| 文件缺失/不可读 | `BUDGET_POLICY_FILE_UNREADABLE` |
| symlink | `BUDGET_POLICY_FILE_SYMLINKED` |
| 大小异常 | `BUDGET_POLICY_FILE_SIZE_INVALID` |
| 未知字段/缺字段/重复 key/非标量/制表符 | `BUDGET_POLICY_FILE_INVALID:<detail>` |
| 整数值写成 `50.0` | `BUDGET_POLICY_VALUE_INVALID:max_live_requests` |
| 任一冻结值不一致（含 soft 两项） | `BUDGET_POLICY_DRIFT:<key>` |
| Controller 被注入非 M0 预算 | `CONTROLLER_BUDGET_NOT_M0_POLICY` |
| pricing 仍为 `REQUIRED_UNVERIFIED` | `LIVE_PRICING_SNAPSHOT_UNVERIFIED`（恒上报，不声称已定价） |
| pricing 被改成摘要/其他值 | `BUDGET_POLICY_PRICE_SNAPSHOT_UNSUPPORTED`（G4-A 无法验证任何价格源） |

- 文件任一字节变化还会改变 `budget_policy` 组件摘要 → `merged_profile_sha256` 变化 → 已签名授权在下一检查点 deny（A10 显式断言）。
- 结论：**常量即冻结契约**；配置改动既被逐字段比较发现，也被闭包绑定发现；价格源未验证，真实计费仍由 `LiveGate`/未部署边界阻断。

---

## 11. 重放 / epoch 契约

- **单次消费**：`consume_execution_authorization()` 在 `pre_reserve` 重跑全量校验后，用 `sha256(authorization_id)` 命名的记录文件 + `O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC` 原子创建；并发两个消费者**恰好一个成功**（A12 双线程断言）。
- 记录内容：`{"schema":"at-m0/authorization-use/v1","authorization_id","run_epoch","consumed_utc"}`，mode `0600`。
- **同 epoch 复用** → `AUTHORIZATION_REPLAYED`；**新 run 使用旧授权 ID / 跨 epoch** → `AUTHORIZATION_EPOCH_MISMATCH`；两者都拒绝。新 run 必须由人类签发新 `authorization_id`。
- **不设计无限复用许可**：无 allowlist、无豁免；授权运行内部的多调用受 `max_calls<=50`、`max_dispatch_attempts<=50`、deadline 约束，而不是靠复用授权。
- 上限：记录数 `>=4096` → `AUTHORIZATION_USE_LOG_FULL`；记录目录位于仓库外、非 symlink、非 group/other 可写、非 candidate uid；记录损坏/symlink → `AUTHORIZATION_USE_RECORD_INVALID/UNREADABLE`（存在即视为已消费，fail-closed）。
- 到期或撤销后 Reserve 侧消费同样拒绝（`AUTHORIZATION_NOT_CURRENT` / `AUTHORIZATION_REVOKED`），且**不落记录**。

**证据**：`test_a12_replay_epoch.py`（19 tests）。

---

## 12. 测试与证据（实际执行）

| 项 | 命令 | 结果 | exit | UTC |
|---|---|---|---|---|
| G4-A 套件 | `PYTHONPATH=src:artifacts/foundation/deps python3.11 -B -m pytest -q -p no:cacheprovider tests/integration/g4_a --junitxml=artifacts/g4/g4a/junit-g4a.xml` | **223 passed, 0 failed**（97.87s） | **0** | 2026-11-18T16:39:57Z→16:41:36Z |
| 必跑回归（全量） | `… pytest -q tests/unit/security tests/integration/g3c tests/integration/g3d tests/integration/g3_bridge` | **1 failed, 404 passed**（405 collected，96.12s） | **1** | junit `timestamp=2026-11-18T16:35:23Z` |
| 必跑回归（排除冻结基线断言） | 同上 + `--deselect tests/integration/g3d/test_d3_contract.py::test_runner_does_not_modify_product_src` | **404 passed, 1 deselected**（96.13s） | **0** | junit `timestamp=2026-11-18T16:38:11Z` |
| ruff | `artifacts/foundation/deps/bin/ruff check --no-cache src/autoteacher_m0/security/authorization.py src/autoteacher_m0/security/ed25519.py src/autoteacher_m0/security/live_controller.py tests/integration/g4_a/` | **All checks passed!** | **0** | 2026-11-18T16:35Z |

### 12.1 唯一失败项的归因（不修改、不掩盖）

```text
tests/integration/g3d/test_d3_contract.py::test_runner_does_not_modify_product_src
assert git diff --quiet 4bd48037d98e081c8fb96a246f3fbf3cf60eb38b -- src
```

该用例断言 **`src/` 自 G3-D 冻结基线 `4bd4803` 起字节不变**。G4-A 按任务书授权修改了 3 个 `security/` 文件，因此该冻结契约断言必然失败：

- 不是安全回归：无权限放行、无账本/发送路径变化；
- 不是本轮可修项：修改该测试等于重写历史证据（禁止）；把 `src` 还原等于放弃 G4-A 交付；
- 归因提交：`382b4ee27eba3d31f17ca2c9cd36b1d6332c559c`（`feat: G4-A ...`，3 个 `src/` 文件 +572/−30）；
- 结论：**预期失败**，已在 Lead/Reviewer 处显式登记；G4-E 应以 `--deselect` 该冻结断言取得信号，同时保留本条为“授权后基线必然漂移”的证据。

### 12.2 证据路径（`artifacts/` 已 gitignore，不提交）

| 证据 | 路径 |
|---|---|
| G4-A JUnit / 原始日志 | `artifacts/g4/g4a/junit-g4a.xml`、`artifacts/g4/g4a/pytest-g4a.log` |
| 用例汇总（A01..A15 → 文件/计数/结果） | `artifacts/g4/g4a/cases.json` |
| 回归（全量/排除） | `artifacts/g4/g4a/junit-regression.xml`、`regression.log`、`junit-regression-deselect.xml`、`regression-deselect.log` |
| ruff | `artifacts/g4/g4a/ruff.log` |
| 源码 SHA | `artifacts/g4/g4a/source-sha256.txt` |
| 起止 UTC | `artifacts/g4/g4a/g4a-start.txt`、`g4a-end.txt` |

---

## 13. A01..A15 状态（矩阵逐行）

| Case | 场景（矩阵） | 关键断言 / 错误码 | 测试文件（tests） | 状态 |
|---|---|---|---|---|
| G4-A-01 | 合法合成签名，verifier 通过 | `signature_valid=True`、`billable_send_authorized=False`；LiveGate/CLI/script/Adapter BLOCKED，exit 3 | `test_a01_signature_vs_billable.py`(5) | **PASS** |
| G4-A-02 | 小阶公钥 | `EXTERNAL_AUTHORIZATION_INVALID`；identity 伪造拒绝 | `test_a02_small_order.py`(9) | **PASS** |
| G4-A-03 | 非 canonical / torsion | 非 canonical 公钥与 R、mixed-order 拒绝 | `test_a03_torsion_noncanonical.py`(8) | **PASS** |
| G4-A-04 | R/S/长度非法 | `HUMAN_SIGNATURE_INVALID`/`SIGNATURE_ENCODING_INVALID`；无 traceback | `test_a04_signature_lengths.py`(29) | **PASS** |
| G4-A-05 | 重复 key/非有限数/多余字段 | `EXTERNAL_AUTHORIZATION_INVALID`/`AUTHORIZATION_SCHEMA_FIELDS_INVALID` 等 | `test_a05_strict_json.py`(20) | **PASS** |
| G4-A-06 | bool/float/string 计数 | `BUDGET_VALUES_INVALID`/`DEADLINE_VALUES_INVALID` | `test_a06_integer_types.py`(32) | **PASS** |
| G4-A-07 | 可信密钥/批准路径在候选域 | 仓库内/symlink/可写/候选 uid/Stage 内全部拒绝 | `test_a07_trusted_file_boundary.py`(12) | **PASS** |
| G4-A-08 | 过期/未生效/skew/撤销 | `AUTHORIZATION_NOT_CURRENT+EXPIRED/NOT_YET_VALID`、`AUTHORIZATION_REVOKED` | `test_a08_time_expiry_revocation.py`(17) | **PASS** |
| G4-A-09 | source/runtime/plugin/config/manifest 漂移 | 15 组件闭包；`<ROOT>_MISMATCH`；启动前 deny | `test_a09_binding_closure.py`(6) | **PASS** |
| G4-A-10 | budget/route/model/deadline/tool 差异 | `ROUTE_NOT_APPROVED`、`BUDGET_POLICY_MISMATCH:*`、`BUDGET_POLICY_DRIFT:*` | `test_a10_route_tools_budget.py`(21) | **PASS** |
| G4-A-11 | Markdown/env/flag/自签绕过 | 全部拒绝；文本审计仅辅助（含盲点演示） | `test_a11_bypass_negatives.py`(6) | **PASS** |
| G4-A-12 | 重放/陈旧 scope/run epoch | `AUTHORIZATION_REPLAYED`/`AUTHORIZATION_EPOCH_MISMATCH`；单次消费 | `test_a12_replay_epoch.py`(19) | **PASS** |
| G4-A-13 | 批准后运行时变化 | 三检查点 `BINDING_DRIFT:<CHECKPOINT>:<ROOT>_MISMATCH`；消费前 deny | `test_a13_toctou_checkpoints.py`(13) | **PASS** |
| G4-A-14 | 未注册/轮换密钥 | `UNKNOWN_APPROVAL_KEY`；轮换后旧签名 `HUMAN_SIGNATURE_INVALID` | `test_a14_key_registration_rotation.py`(18) | **PASS** |
| G4-A-15 | 无可达运行时私钥/签发 | AST 扫描仅 `verify`/`is_valid_public_key`；无 seed 字段/PEM；Stage 无密钥 | `test_a15_no_signing_path.py`(8) | **PASS** |

> **证据等级说明**：本轮全部为 **L1-HOST 真实进程**（宿主 Python 3.11.15、`-B`、`PYTHONPATH=src:deps`），未在锁定 OCI 内重跑、未启动容器。矩阵 `required_evidence_level=L2` 未被本轮完全满足；G4-E 必须在 OCI 内复跑本套件。状态 `PASS` 仅指“该层真实执行 + 断言满足”，不得外推为 L2/部署证据。

---

## 14. 残余风险与未主张

| ID | 残余 | 处置/归属 |
|---|---|---|
| R1 | 只有 L1-HOST 证据，无 OCI/L2 重跑 | G4-E 在锁定 OCI 内复跑 `tests/integration/g4_a` |
| R2 | G3-D 冻结断言 `test_runner_does_not_modify_product_src` 因授权改码必然失败 | 显式登记（§12.1）；不修改历史测试；G4-E 用 deselect 取信号 |
| R3 | 闭包组件路径表是 G4-A 契约声明，未由独立构建产物证明；runtime/deps/stage 在 fixture 中为 TEST_ONLY 占位 | G4-B 冻结权威 manifest 并替换占位；G4-E 校验 manifest 哈希 |
| R4 | 新 API 未加入 `security/__init__.py`（写域外） | 调用方从 `security.authorization` 直接导入；后续包维护提交补齐（需 Lead 授权） |
| R5 | 单独 `load_execution_authorization` 无法排除 candidate Stage | 必须经 `TrustedLiveController` 组合；G4-C 接线时保持 |
| R6 | 单次使用日志是外部目录记录，未签名/未锚定；可信目录 owner 可删除记录 | 部署侧 root 只读/受保护目录；无 per-run OS 身份（P2-RUN-IDENTITY 仍未决） |
| R7 | 检查点到发送之间无 OS 级不可变保证 | G4-C 以 prepared/claim 摘要绑定 + 紧邻检查；G4-H 用只读挂载 |
| R8 | pricing `REQUIRED_UNVERIFIED`；$10 是工程硬顶，不是供应商侧上限 | G4-C/G4-H 提供并核验价格源；不得声称“不会超过 $10” |
| R9 | 密钥轮换/吊销策略由人类定义；本模块只实现“注册即信任、移除即撤销” | G4-H 定义公钥注册/轮换/吊销 SOP |
| R10 | `signature_valid` 只证明 Ed25519 数学有效，不证明人类意图 | 人类信任根与审批流程是 G4-H 前置 |
| R11 | 网络守护为进程内 socket patch，不能证明子进程/内核无网络 | 本轮不启动子进程发送；容器侧证据在 G3-D/G4-C |
| R12 | 权限检查基于 mode/owner，不覆盖 ACL/xattr；测试以 root 运行 | 部署侧 root 只读目录；如需 ACL 支持由 G4-H 评估 |

**未主张**：真实人类授权已部署、真实密钥存在、真实计费可控、供应商硬上限、E5-PreLive Full、G4 PASS、G5/G6 可启动。

---

## 15. 声明与 STOP

- 本文件只覆盖 **G4-A（无 Key 授权校验器）**；最高状态 **`PASS_NO_KEY_AUTH_VALIDATOR`**。
- **`HUMAN_AUTHORIZATION_DEPLOYED` 未达成**，`G4-H-01..06` 仍 `BLOCKED`，`G5` 不得启动。
- 全程 0 真实 Key、0 模型、0 外部 HTTP/TCP、0 容器启动、0 `podman pull`；`LiveGate=BLOCKED`；`run_live.sh` exit 3。
- 本文件不构成授权、不构成人类审批、不替代独立 Reviewer。
- **STOP**：不进入 G4-C；等待 Lead/独立 Reviewer 审阅与后续维护者决策。
