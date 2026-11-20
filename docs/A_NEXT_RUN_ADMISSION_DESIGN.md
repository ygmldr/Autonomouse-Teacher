# A-PR1 / A2 — Run-level ExecutionAuthorization 一次性消费接线设计 ADR（no-key，设计阶段）

- **文档 ID**：`A-NEXT-A-PR1-A2-DESIGN-v1`
- **状态**：`DESIGN_ONLY` / **未实现、未接线、未运行任何新增测试**；等待 Independent Reviewer 判定“无安全降级”后才进入实现阶段。
- **工作树 / 分支**：`/root/Autonomous Teacher/worktrees/a-next-run-admission` / `feat/a-next-run-admission`
- **基线**：`fd1d3a6d101f17e6a86d7c43f06c630326e3e3af`（= 复核快照 `work/g4r`；产品实现冻结 SHA `d33e0aab…`，`src/` 自 `d33e0aa` 起未变）
- **作者角色**：Implementer（F-C）；**不是** Lead、**不是** Independent Reviewer
- **本轮范围**：只做设计与证据梳理。**不新增生产接线实现、不改 `src/`、不写测试代码、不构建 Packet。**
- **硬边界**：0 真实 Key / 0 真实 Provider / 0 外部 HTTP/TCP / 0 Live。`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT` 全部不变。人类签名根 / Key Broker / Egress / Watchdog **不部署**。
- **上游依据**：`01_LEADA_AGENT_HANDOFF.md` A2；`AUDIT_REQUESTS.md` A-Q3；`docs/REVIEW_G4R_INDEPENDENT.md` P2-02（开放式 scope gap）；`COMMON_REVIEW_AND_ROADMAP.md` A-01。
- **本文件不构成**任何 PASS、任何 Live 授权、任何 G4-H1 准入凭据。

---

## 0. 摘要（给 Reviewer 的一页）

### 0.1 要解决的问题

`consume_execution_authorization()` 在 G4-R 中已实现模块级“恰一次消费”的原子发布（tmp→fsync→ `os.link` no-replace→目录 fsync，`AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN` 等 fail-closed 分类），**但生产 `src/` 内没有任何 Controller/Launcher 调用方**（§1.2 grep 证据）。因此：

> 模块级测试 PASS ≠ 真实 Run 存在强制的“一次性执行授权”入口。

A-PR1/A2 的目标：设计一个 **Run-level 的一次性入口**（不是每个 Provider dispatch 消费一次），把外部人类签名的 `ExecutionAuthorization` 与受信 Run 启动、Broker Reserve/Claim、Fake/受限 dispatch 绑定起来；同一 Run 内已签预算内的多次合法 calls **不得**被误判为重放。

**本阶段只交设计**；实现与 L2 取证在 Reviewer 判定后进行。

### 0.2 设计要点（一句话版）

1. **一次消费发生在 Run 启动之前**：受信 Launcher/入口进程先完成“加载授权→验签/绑定/有效期/撤销→派生 run_epoch→`consume_execution_authorization()` 恰一次”，成功后才允许构造 Broker/Fake/Controller；失败路径 Broker/Fake 进程**根本不存在**（结构上 0 Reserve/0 Fake/0 Attempt）。
2. **Run 内多次 dispatch 用独立 token，不再消费授权**：新增受信 principal 生成的 per-dispatch `DispatchAdmissionToken`（in-process、不可 JSON 构造、单次使用、绑定 run_id/run_epoch/call_id/prepared_digest/payload_digest、跨 Run 不可复用、默认拒绝），在 **pre-Reserve** 处消费，先于任何 Broker Reserve。
3. **run_epoch 与 business call_id 分离**：run_epoch 由受信 Admission 文档（`admission_id` + `launcher.admission_nonce`）确定性派生；call_id 仍由现有 request identity 决定。二者在所有审计中分开记录，绝不互相推导。
4. **审计**：新增 append-only run-admission JSONL（身份/epoch/签名闭包摘要/拒绝 reason/是否消费，**不含 Key/原始请求**），并对 dispatch-window 记录做**附加字段**而非改写既有语义；历史 hold **只读计数、永不改写**。
5. **本轮只做 test-only/no-key harness**：受保护临时签名/授权 fixture + Fake Broker + Fake Backend + 双 principal 布局；不新增 Live allow path；LiveGate/`run_live.sh`/CLI/Adapter 均不受影响。
6. **依赖 A1**：A1 的 `_read_use_record` body-id 校验必须保持“body id 不匹配 → `AUTHORIZATION_USE_RECORD_INVALID`（不是 REPLAYED）”；A2 只调用公开 `consume_execution_authorization()`，不依赖 A1 私有函数；接口契约见 §8。

### 0.3 明确不做（本 ADR 与 A-PR1 阶段）

- 不部署任何真实人类签名根、Key Broker、Egress Proxy、Watchdog 服务。
- 不读/注入真实 Key，不发起真实 Provider 请求，不运行 Live，不改变 `LiveGate`。
- 不改变 `src/` 现有执行语义；不改冻结 Packet/Review/Matrix；不改 LeadB 的 `m1_*`。
- 不把“host 负例 PASS”外推为端到端/L2 强制；L2 由 A-PR3/A4 在独占窗口完成。

---

## 1. 现网调用链证据（A-Q3 直接回答）

### 1.1 关键源码位置（基线 `fd1d3a6`）

| 组件 | 位置（file:line） | 现状 |
|---|---|---|
| `ExecutionAuthorization`（签名文档） | `src/autoteacher_m0/security/authorization.py:333` | 外部文件、Ed25519 验签、绑定 5 root、route/tools/budget/deadline、有效期 |
| `AuthorizationDecision`（inspection） | `…/authorization.py:350` | `billable_send_authorized` 永远不能为 true |
| `load_execution_authorization()` | `…/authorization.py:478` | 完整离线校验；失败返回 reasons，不消费 |
| `require_execution_authorization()` | `…/authorization.py:700` | fail-closed 包装 |
| `AuthorizationUse` | `…/authorization.py:795` | `authorization_id`, `run_epoch`, `consumed_utc`, `record_path` |
| `_read_use_record()` | `…/authorization.py:802` | 读最终记录：`O_NOFOLLOW`、size 上限、`nlink>2` 拒绝、group/world-writable 拒绝、严格 schema；返回 **run_epoch** |
| `_read_use_record_settled()` | `…/authorization.py:850` | 对空/半写/坏 JSON 的**有界**重试，超界仍 INVALID |
| `_replay_reason()` | `…/authorization.py:872` | 同 epoch → `AUTHORIZATION_REPLAYED`；异 epoch → `AUTHORIZATION_EPOCH_MISMATCH` |
| `_fsync_directory()` / `_count_use_log_entries()` | `…/authorization.py:918` / `:942` | 目录持久化与容量/临时文件计数 |
| `consume_execution_authorization()` | `…/authorization.py:988` | 模块级恰一次消费；`DURABILITY_UNKNOWN` 在 `:1095` |
| `TrustedSendGate.authorize/consume`（per-dispatch send capability） | `src/autoteacher_m0/security/egress.py:1983` / `:2210` | 现有 per-dispatch 单次 capability（in-process identity registry） |
| Controller 每 dispatch 的 send cap 消费点 | `src/autoteacher_m0/bridge/controller.py:1153` | 仅消费 **send** capability；**不消费** ExecutionAuthorization |
| Controller 构造/启动入口 | `…/controller.py:2235`（`main`）、`:2285`（`TrustedController(...)`） | 读 config → `load_admission` → **start Broker** → start Fake → AttemptJournal → Controller → `reconcile_on_startup` → server |
| 受信 Launcher 入口（现有） | `scripts/g4/stage/trusted_entry_g4c.py:384`（`main`），`:458` 调 `controller.main(..., dispatch_gate=gate)` | 只构造 `TrustedSendGate`（binding closure + F5 合成撤销），**不加载 ExecutionAuthorization、不消费 use record** |
| 旧 Launcher 入口 | `scripts/g3d/stage/trusted_entry.py:216` | 无 gate，更无 run admission |
| Admission 文档（run identity） | `src/autoteacher_m0/bridge/admission.py:47`（`Admission`），`:70`（`load_admission`） | 已有 `admission_id/run_id/admission_nonce/sha256/launcher_uid/limits/tool_schemas` |
| Inspect-only Controller | `src/autoteacher_m0/security/live_controller.py:132` | 唯一调用 `load_execution_authorization` 的生产模块；**只 inspect，永远 BLOCKED，从不 consume** |

### 1.2 grep 结论（A-Q3：谁在 prod 调用？答案：无人）

命令（基线 `fd1d3a6`，只统计 `src/` 与 `scripts/`）：

```bash
$ grep -rn "consume_execution_authorization" src --include=*.py
src/autoteacher_m0/security/authorization.py:988:def consume_execution_authorization(*, use_log_dir: Path, run_epoch: str,
# → 只有定义；0 个生产调用方。

$ grep -rn "load_execution_authorization\|require_execution_authorization" src --include=*.py
src/autoteacher_m0/security/live_controller.py:29:    load_execution_authorization,
src/autoteacher_m0/security/live_controller.py:132:        decision = load_execution_authorization(
# → 仅 inspect-only 的 live_controller；不消费、不发射、永远 BLOCKED。
```

非生产（测试/探针）调用方（**不能**当作 prod 接线证据）：

```text
tests/integration/g4_a/g4a_support.py:25,280        TEST_ONLY fixture 包装
tests/integration/g4r_auth/test_r1_atomic_use_record.py:39,117,368
scripts/g4/e5_probe.py:56,205                       离线探针
scripts/g4r/r1_independent_probe.py:41,71           独立探针
scripts/g4/build_packet.py:311                      仅历史字符串注入
```

**结论（照实承认）**：A-Q3 = **没有生产调用方**。当前 dispatch 链（Broker Reserve→Claim→Attempt→`TrustedSendGate.authorize/consume`→Fake）**没有** run-level 一次性执行授权；`consume_execution_authorization()` 只是被测试/脚本调用的模块级能力。`docs/REVIEW_G4R_INDEPENDENT.md` P2-02（`:308`）的记录与本 ADR 一致。

### 1.3 现状时序（as-is，无 run admission）

```text
Trusted Launcher (scripts/g4/stage/trusted_entry_g4c.py, trusted container uid 0)
  │  1. 读 config/policy；policy 校验；binding_drift("pre_start")
  │  2. _build_gate(policy) → TrustedSendGate(binding pre_dispatch + 可选 F5 撤销文件)
  ▼
controller.main(--config, dispatch_gate=gate)          [controller.py:2235]
  │  3. load_admission()（Admission 文档，run_id/nonce/limits/tools）
  │  4. **BrokerClient.start()**                        ← 先起 Broker
  │  5. FakeBackend(...)                               ← 再起 Fake
  │  6. AttemptJournal
  │  7. TrustedController(dispatch_gate=gate, dispatch_journal, request_lifecycle,
  │                      recovery_diagnostics)          [controller.py:2285]
  │  8. reconcile_on_startup(receipt_dir)；register_admission()
  │  9. BridgeServer.serve_forever()
  ▼
每 dispatch（Controller 内部）：
  _prepare_checked → quota/identity → **Broker Reserve** → Claim → begin_attempt
    → TrustedSendGate.authorize(...)  [egress.py:1983]  ← per-dispatch send capability
    → TrustedSendGate.consume(...)    [egress.py:2210, controller.py:1153]
    → Fake send → receipt/observation → settle/fail
```

**缺口**：第 3~9 步之间没有“本次 Run 的人类签名授权已被恰一次消费”的门；也没有 per-dispatch 的“Run 准入 token”。`TrustedSendGate` 的 capability 只证明“这次 send 有本进程 mint 的短期凭证”，**不证明整个 Run 有外部授权**（它绑定的 `authorization_id/auth_epoch` 来自 policy 配置，未与 `ExecutionAuthorization` 的签名文档/消费记录闭环）。

### 1.4 需要保留的既有属性（不得退化）

1. `consume_execution_authorization()` 的原子发布、恰一次、fail-closed 分类（REPLAYED/EPOCH_MISMATCH/INVALID/UNREADABLE/WRITE_FAILED/LOG_FULL/DURABILITY_UNKNOWN）**保持不动**；
2. `TrustedSendGate` 现有 pre_start/pre_dispatch binding 检查与 F5 撤销检查**保留**，run admission 是**附加层**而非替代；
3. `AttemptJournal`/Broker/Receipt/Observation 的账本语义、`SETTLEMENT_UNCERTAIN` 保守占用、Broker 终态权威、无自动重试/重发**全部不变**；
4. `controller.main`/`TrustedController`/trusted entry 的**默认（无 run admission）行为逐字节不变**——实现阶段以可选参数/可选 config 块接入，旧测试无需改动；
5. `LiveGate`/`run_live.sh`/CLI `--live`/Adapter 四入口**永久 BLOCKED 不变**。

---

## 2. 威胁模型与安全不变量

### 2.1 参与方与信任边界

| 参与方 | 运行位置/UID | 信任级别 | 能做什么 |
|---|---|---|---|
| 维护者（人类，本阶段**不参与**） | 仓库外离线 | 唯一信任根（未部署） | 离线生成 Ed25519 签名授权 + 公钥/撤销文件 |
| 受信 Launcher/入口 | trusted 容器 uid 0（测试为宿主 root 进程） | 受信代码 + 受信配置；**不是**人类本身 | 校验并一次性消费授权、启动 Broker/Controller、生成 per-dispatch token |
| 受信 Controller/Broker/Fake | trusted 容器/sidecar 进程 | 受信（代码在当前冻结树） | Reserve/Claim/Attempt/Receipt/Settlement；Fake 发送 |
| Candidate / DSH Runtime | candidate 容器 uid 65534、`--network none`、只读、非 root | **不可信** | 只能经白名单 UDS 发请求；不能读写 trust 文件/DB/Key |
| 外部 Key Broker / Egress / 人类签名根 | 未部署 | — | 本阶段不存在 |

### 2.2 不变量（A-PR1/A2 必须维持）

- **INV-R1**：一个 `ExecutionAuthorization`（以 authorization_id + 外部签名文件为身份）在一个 Run 内**至多一次**成功消费；成功消费是进入 Broker Reserve 的**必要条件**。
- **INV-R2**：同一 Run 内，已签预算/期限内的多次合法 business calls 不得被误判为重放；它们不消费授权，只消费 per-dispatch admission token。
- **INV-R3**：Run 身份（run_id/run_epoch）与 business call 身份（call_id/request identity）严格分离；任何审计/校验不得用其中一个替代另一个。
- **INV-R4**：任何授权校验依赖（签名/公钥/撤销/绑定/有效期/工具 schema/预算/期限）任一失败、或状态未知（含 `DURABILITY_UNKNOWN`）→ **不进入 Reserve/Claim/Fake**，且不产生新的 Attempt。
- **INV-R5**：Cookie/JSON/复制 dataclass/别的 Run 的 token 一律不是凭证；per-dispatch token 只能由本次 Run 的受信 principal 生成并验证，默认拒绝。
- **INV-R6**：历史 `PENDING/SETTLEMENT_UNCERTAIN` hold 不被 run admission 路径改写、释放或重结算；Broker 终态仍然权威。
- **INV-R7**：run admission 模块/入口**不得**引入 Key 读取、环境变量开关、网络/Provider 调用、Live allow path；`LiveGate` 状态不变。
- **INV-R8**：授权/审计不记录 Key、原始 prompt/messages/tool 参数、session 文本或宿主敏感路径；只记录封闭枚举、有界标识符与 SHA-256 摘要。

### 2.3 主要攻击面（设计需覆盖）

1. 伪造/篡改授权文件、未知公钥、过期/未生效、撤销窗口；
2. 同一授权被并发/重启/另一 Run 重放；
3. Use record 被替换为“别的 authorization_id 的合法记录”（A1/P2-01 场景）；
4. 启动时崩溃/掉电导致“已消费但持久性未知”；
5. 伪造/copied per-dispatch token、跨 Run 复用、序号回退、digest 绑定错配；
6. tool schema / binding 在启动后漂移（TOCTOU）；
7. 通过环境变量/CLI flag/自签 JSON 试图绕过（必须无效）；
8. 候选进程尝试读取/篡改 trust 文件或 use log（OS 边界 + 权限测试由既有机制覆盖，本 ADR 不新增信任假设）。

---

## 3. Run-level 一次性消费入口设计

### 3.1 新组件与职责

新增（实现阶段）文件：`src/autoteacher_m0/bridge/run_admission.py`（trusted-domain，纯离线，无 Key/网络 import）：

| 组件 | 职责 |
|---|---|
| `RunIdentity`（frozen dataclass） | `run_id`, `admission_id`, `admission_sha256`, `admission_nonce`, `run_epoch`；由受信 Admission 文档派生 |
| `RunAdmissionContext`（受信 principal） | 持有 `RunIdentity`、授权摘要、绑定摘要、运行 deadline、有效 max_calls；**唯一**可 mint/consume `DispatchAdmissionToken`；状态机 `ACTIVE/BLOCKED/CLOSED` |
| `DispatchAdmissionToken`（frozen dataclass） | 仅由 `RunAdmissionContext.begin_dispatch()` 生成；字段见 §4.2；无 JSON 构造入口 |
| `RunAdmissionJournal`（append-only JSONL） | 写 run admission 审计（§5）；写失败视为 fail-closed |
| `begin_run_admission(...)` | 受信 Launcher 调用的**唯一** run-level 入口：校验→派生 run epoch→`consume_execution_authorization()` 恰一次→审计→返回 `RunAdmissionContext` |
| `RunAdmissionError`（带稳定 code/reasons） | 拒绝时携带封闭枚举 reasons；调用方据此退出，**不启动 Broker** |

不新增公开 HTTP/socket/CLI 入口；不改变 `security/__init__` 的既有公开语义（可追加内部导出）。

### 3.2 启动时序（to-be，A-PR1 实现目标）

```text
Trusted Launcher / Trusted Entry（trusted 容器 uid 0；测试为宿主受信进程）
 │
 │ (A) 启动前静态检查（沿用 trusted_entry_g4c.py 现有 1~3 步）
 │     1. 读 config/policy（strict no-extra）；policy 必须声明 run_admission block
 │     2. load_admission(config["admission_path"])  [admission.py:70]
 │     3. observed_bindings 复算 + binding_drift("pre_start") 必须为空
 │
 │ (B) Run admission（本 ADR 新增；**在任何 Broker/Fake/Controller 构造之前**）
 │     4. begin_run_admission(
 │            authorization_path, trusted_keys_path, revocation_path,
 │            repo_root, expected=approved_bindings, approved_route,
 │            actual_tools=<runtime-approved tool set>,
 │            budget_scope, use_log_dir=<trusted state dir>,
 │            admission=<Admission doc>, run_epoch=<派生>,
 │            now=<trusted clock>)
 │        ├─ load_execution_authorization(checkpoint="pre_start")  [authorization.py:478]
 │        │    ├─ 外部文件/external-regular/no-symlink/权限/大小
 │        │    ├─ Ed25519 签名 + trusted key_id + 有效期（issued≤not_before≤now<expires）
 │        │    ├─ 5 个绑定 root == approved（+ observed 复算）
 │        │    ├─ route == 唯一批准 route；allowed_tools == actual_tools
 │        │    ├─ budget（scope/per_call≤total≤10/max_calls≤50）与 deadline 边界
 │        │    └─ revocation 文件：authorization_id ∉ revoked_ids
 │        ├─ 派生 run_epoch（§3.4）并校验 run_epoch 格式
 │        ├─ consume_execution_authorization(use_log_dir, run_epoch)  [authorization.py:988]
 │        │    ├─ 成功 → outcome=CONSUMED_KNOWN；记 use_record sha256
 │        │    └─ 失败 → 按 §3.5 映射为稳定 outcome（REPLAYED/EPOCH_MISMATCH/
 │        │              INVALID/UNREADABLE/WRITE_FAILED/DURABILITY_UNKNOWN/...）
 │        ├─ 生成 RunAdmissionContext（仅成功路径；否则 BLOCKED 上下文用于审计后退出）
 │        └─ 写 audit JSONL（intent + outcome 两阶段，§5.3）→ 写失败 = fail-closed
 │
 │  若 (B) 失败：写 stderr 稳定 code（如 RUN_ADMISSION_DENIED:<REASON>）→ exit ≠ 0
 │               Broker/Fake/Controller **从未构造** → 0 Reserve / 0 Fake / 0 Attempt（结构性）
 │
 │ (C) 既有受信链（默认行为不变，仅多一个受信对象）
 │     5. _build_gate(policy)（TrustedSendGate：binding pre_dispatch + F5 撤销）
 │     6. controller.main(--config, dispatch_gate=gate, run_admission=context)  [新增可选参数]
 │        ├─ controller.main 在 **start Broker 之前**校验 context.is_active() 且
 │        │    context.constructor_owner == 本进程/本次启动；否则稳定 exit code、
 │        │    不启动 Broker/Fake
 │        ├─ start Broker → Fake → AttemptJournal → TrustedController → reconcile → serve
 │
 │ (D) 每 dispatch（Controller 内部；新增 admission token 检查，仍早于 Reserve）
 │     7. _prepare_checked（现有）→ quota/identity（现有）
 │     8. context.begin_dispatch(call_id=prepared.call_id, prepared_digest, payload_digest,
 │                               ordinal=next)  → DispatchAdmissionToken
 │     9. context.consume_dispatch(token, call_id, prepared_digest, payload_digest)
 │          ├─ 失败 → 稳定 deny code；**在 `_broker_reserve()` 之前抛出** → 0 新 Reserve
 │          └─ 成功 → 标记 token 已消费
 │    10. Broker Reserve → Claim → begin_attempt（现有）→ TrustedSendGate.authorize/consume
 │        （现有，per-dispatch send capability）→ Fake（现有）
 │    11. dispatch-window / request-lifecycle 附加 run admission 字段（§5.4）
```

**关键顺序约束（实现验收点）**：

- `begin_run_admission` 必须在 `BrokerClient(...).start()` 之前；该函数内部不 import/启动 Broker/Fake、不写 Attempt DB。
- `consume_execution_authorization` 恰一次，且仅在 run-level（**每个 Run 一次**）；`TrustedSendGate` 继续按 dispatch mint/consume，二者互不替代。
- token 的 mint 在 `_prepare_checked` 成功后、`begin_attempt` 之前；consume 在 `_broker_reserve()` 之前（结构上保证 token 拒绝 → 0 新 Reservation）。
- 失败路径不得调用 `reconcile_on_startup`、不得写 Attempt/Reservation/Claim（历史 hold 只在审计中**只读计数**）。

### 3.3 Run-level 消费入口契约（公开 API 设计；实现阶段形态）

```python
# src/autoteacher_m0/bridge/run_admission.py（设计草案；本 ADR 不实现）

RUN_EPOCH_PREFIX = "run-"
RUN_ADMISSION_SCHEMA = "m0.g4r.run-admission.v1"
DISPATCH_TOKEN_SCHEMA = "m0.g4r.dispatch-admission-token.v1"

@dataclass(frozen=True)
class RunIdentity:
    run_id: str
    admission_id: str
    admission_sha256: str      # Admission 文档 sha256（trusted launcher 计算）
    admission_nonce: str       # 32-hex；Admission.launcher.admission_nonce
    run_epoch: str             # "run-" + sha256(canonical(...))[:32]（§3.4）

def derive_run_epoch(*, admission_id: str, admission_nonce: str) -> str:
    """确定性派生；同一 Admission → 同一 epoch；不同 Run → 不同 epoch。"""

def begin_run_admission(
    *,
    identity: RunIdentity,
    authorization_path: Path,
    trusted_keys_path: Path,
    revocation_path: Path,
    repo_root: Path,
    expected_bindings: ExpectedBindings,
    approved_route: ApprovedRoute,
    actual_tools: tuple[str, ...],
    admission_tool_schemas: tuple[tuple[str, str], ...],
    budget_scope: str,
    use_log_dir: Path,
    admission_limits: Mapping[str, int],   # max_calls/max_attempts/deadline_ms/...
    journal_path: Path,
    now: datetime | None = None,
    observed_bindings: Callable[[], ExpectedBindings] | None = None,
) -> RunAdmissionContext:
    """Run-level 唯一入口。成功返回 ACTIVE context；任何拒绝抛 RunAdmissionError。

    调用者（Trusted Launcher）必须在 Broker/Fake/Controller 构造之前调用。
    """

class RunAdmissionContext:
    # 只读属性
    identity: RunIdentity
    authorization_id: str
    authorization_digest: str          # sha256(canonical(signed payload bytes))
    approver: str
    key_id: str
    effective_max_calls: int
    run_deadline_monotonic: float
    state: Literal["ACTIVE", "BLOCKED", "CLOSED"]
    consumed: Literal["YES"]           # ACTIVE 时必为 YES
    use_record_sha256: str

    def begin_dispatch(self, *, call_id: str, prepared_digest: str,
                       payload_digest: str, payload_length: int,
                       scope_id: str, route_id: str, model_id: str
                       ) -> DispatchAdmissionToken: ...
    def consume_dispatch(self, token: object, *, call_id: str,
                         prepared_digest: str, payload_digest: str
                         ) -> str | None: ...   # None=accepted；否则稳定拒绝码
    def close(self, *, reason: str) -> None: ...
```

**为什么消费只发生在 run 启动**（设计论证）：

- 语义：人类签名的是“这一整次受控 Run”的预算/期限/路由/工具/绑定，而不是“每个 dispatch 一条授权”；per-dispatch 消费会迫使人类为每个 call 重新签名，并使崩溃/重试语义恶化。
- 安全：Run 启动即消费，使“未消费就发送”在结构上不可能；Run 内多次 dispatch 受 token + 既有 `TrustedSendGate` + Broker 预算三重约束。
- 可恢复性：消费记录 + Admission nonce 确定性 epoch 让“崩溃后同一 Run 重启”得到稳定 REPLAYED（不是 EPOCH_MISMATCH），可审计、不可自动重发。

### 3.4 run_epoch 与 Run 身份的派生

```text
run_epoch = "run-" + lowercase_hex(
    sha256( canonical_json({
        "schema": "m0.g4r.run-epoch.v1",
        "admission_id": admission.admission_id,       # 受信 Admission 文档
        "admission_nonce": admission.admission_nonce, # 每次 launcher 启动唯一
        "run_id": admission.run_id
    }) )
)[:32]
```

- **确定性**：同一份 Admission（同一 `admission_nonce`）在同一 Run 的任意重启进程中得到同一 epoch → `consume` 对已发布记录返回 `AUTHORIZATION_REPLAYED`（正确：该授权已被本 Run 消费）。
- **唯一性**：新的 Run 必须使用新的 Admission（`admission_nonce` 唯一，且 `AttemptJournal.register_admission` 已拒绝重复 admission_id）；同一授权文件被另一 Run 使用时 epoch 不同 → `AUTHORIZATION_EPOCH_MISMATCH`（正确：跨 Run 复用被拒）。
- **不混用**：`run_epoch` 不出现在 call_id/request identity 中；`call_id` 继续由现有 `prepared_call_id`/request identity 生成（`controller.py` 现有逻辑），二者在审计中并列记录。
- **格式**：符合 `authorization.py::_IDENTIFIER` 的 `[A-Za-z0-9._:-]{1,128}`；实现阶段加单元测试（含非法字符/超长）。

> 备选方案与否定理由：
> 1. 随机 epoch 由 launcher 生成并持久化：crash-before-persist 会把同 Run 重启误判成 EPOCH_MISMATCH（证据语义错误）；migration/多实例恢复复杂。**否决**。
> 2. 直接用 authorization_id 作 epoch：无法区分“同 Run 重试”与“另一 Run 复用同一授权”，丢失跨 Run 证据。**否决**。
> 3. 每 dispatch 一个 epoch：违反 run-level 语义，且会让 REPLAYED/EPOCH_MISMATCH 分类退化。**否决**。

### 3.5 consume 结果 → Run admission outcome 映射（稳定、封闭）

`consume_execution_authorization()` 的异常 reasons 已由 A1/P2-03 固化；run admission 按**原因集合**映射，不解析自由文本：

| consume 结果（reasons, 首项） | Run admission outcome | consumed | 允许重试？ | 下步 |
|---|---|---|---|---|
| 成功返回 `AuthorizationUse` | `CONSUMED_KNOWN_DURABLE` | YES | 否（已消费） | 启动 Broker/Controller |
| `AUTHORIZATION_REPLAYED` | `DENIED_ALREADY_CONSUMED_SAME_RUN` | NO（本 attempt 未消费；由同一 Run 先前 attempt 消费） | 否（需人工对账） | exit ≠0；不启动 Broker |
| `AUTHORIZATION_EPOCH_MISMATCH` | `DENIED_ALREADY_CONSUMED_OTHER_RUN` | NO | 否（需新授权 + 新 Run） | exit ≠0 |
| `AUTHORIZATION_USE_RECORD_INVALID` / `AUTHORIZATION_USE_RECORD_UNREADABLE` | `DENIED_RECORD_INVALID` | NO（无法证明） | 仅 operator 修复后；自动否 | exit ≠0 |
| `AUTHORIZATION_USE_LOG_WRITE_FAILED` / `AUTHORIZATION_USE_LOG_FULL` / `AUTHORIZATION_USE_LOG_INVALID:*` | `DENIED_LOG_UNAVAILABLE` | NO | operator 处理后可用**同一**授权重试（未发布最终记录） | exit ≠0 |
| `AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN` | `DENIED_DURABILITY_UNKNOWN` | **UNKNOWN**（最终记录已可见=已花掉；目录 fsync 失败） | 否（同一授权后续重试会 REPLAYED） | exit ≠0；run 记 `BLOCKED_PENDING_RECONCILE`；不启动 Broker |
| `AUTHORIZATION_NOT_CURRENT` / `AUTHORIZATION_REVOKED` / `RUN_EPOCH_INVALID` | `DENIED_AUTHORIZATION_INVALID` | NO | 否（需新授权） | exit ≠0 |
| 任何 `EXTERNAL_AUTHORIZATION_INVALID:*` / 签名/绑定/route/tools/budget/deadline 失败 | `DENIED_AUTHORIZATION_INVALID` | NO | 否 | exit ≠0 |
| 未预期异常 | `DENIED_INTERNAL` | NO/UNKNOWN（保守） | 否 | exit ≠0；审计标 `unexpected` |

实现阶段要求：映射函数是**纯函数 + 单元测试矩阵**；不得把 `UNKNOWN` 当作成功或“未消费”处理；`AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN` 必须映射为“不发送 + 不确定”，并在 run audit 中保留该状态（Reviewer 观察-2 明确要求）。

### 3.6 预算/期限的有效上界

- `effective_max_calls = min(authorization.budget.max_calls, admission.max_calls)`；token ordinal 超过即 deny（`RUN_BUDGET_CALLS_EXCEEDED`），**先于** Reserve。
- run deadline：`run_deadline_monotonic = start_monotonic + min(authorization.deadline.total_seconds, admission.deadline_ms/1000)`；dispatch 前检查剩余时间，超时 deny（`RUN_DEADLINE_EXCEEDED`），不 Reserve。
- 金额/单次/总预算的**权威仍是 Broker**（现有）；run admission 不复制价格逻辑，不改变 Broker 的 Reserve/结算语义。`per_call_cap/total_cap` 只做启动时一致性校验（与 admission 限制不矛盾），运行期金额由 Broker 判。
- `max_attempts`：run admission 只按 dispatch 计数；单个 dispatch 内部 existing `max_attempts`/deadline 语义不变。

### 3.7 绑定与工具面

启动时（在 consume 之前）完成并记录：

1. `expected_bindings`（launcher 从受信 policy 读取）vs `observed_bindings`（从 `/project` + 声明输入复算）→ `binding_drift("pre_start")` 必须为空；同时保留现有 `TrustedSendGate` 的 `pre_dispatch` 检查（TOCTOU 双点）。
2. `actual_tools`：来自受信 policy 的 approved tool set + `Admission.tool_schemas` 的 (name, schema_sha256) 对；必须与 `authorization.allowed_tools` **逐元素相等**（顺序规范化后）且 schema digest 与 runtime-policy 一致 → `ADMISSION_TOOL_SCHEMA_MISMATCH`。
3. `tool_set_sha256 = sha256(canonical({"names": sorted(names), "schemas": {name: sha256}}))`，写入 run audit 与 manifest 级引用（后续 Packet）。
4. `merge`：`authorization.bindings`（5 root）必须等于 expected（`mismatches()` 空）；`authorization.route` 必须等于唯一 approved route（逐字段）。
5. 撤销：`revoked_ids`（authorization.py 的外部撤销文件）包含 authorization_id → deny；若 trusted policy 同时配置 F5 合成撤销文件（`TrustedSendGate.revocation_path`），则两处都检查（run-level 启动一次 + dispatch-level pre_send 现有机制）。

---

## 4. Per-dispatch admission token 设计

### 4.1 定位

`TrustedSendGate` 的 `TrustedSendAuthorization` 解决“**这一次 send** 有本进程 mint 的短期 capability”；新的 `DispatchAdmissionToken` 解决“**这次 dispatch 属于一个已准入的 Run**”。两者叠加：

```text
RunAdmissionContext（run-level，本 ADR 新增）
   └── 每个 dispatch：DispatchAdmissionToken（本 ADR 新增，pre-Reserve 消费）
         └── 每个 send：TrustedSendAuthorization（现有，pre-dispatch 消费）
               └── Fake 发送（现有）
```

### 4.2 Token 字段（frozen dataclass；无 JSON 构造）

```python
@dataclass(frozen=True)
class DispatchAdmissionToken:
    schema_version: str          # "m0.g4r.dispatch-admission-token.v1"
    run_id: str
    run_epoch: str
    authorization_id: str
    dispatch_ordinal: int        # 从 1 开始单调递增（每 Run 独立）
    scope_id: str
    call_id: str                 # business identity（与 run_epoch 严格分离）
    prepared_digest: str
    payload_digest: str
    payload_length: int
    route_id: str
    model_id: str
    issued_utc: str
    expires_utc: str
    principal_instance_id: str   # 本 Run admission context 的随机实例 id
    nonce_sha256: str            # 32B process-local nonce 的 sha256（nonce 本身不落盘/不打印）
    synthetic: bool = True
```

### 4.3 生成/验证主体与规则

- **生成**：仅 `RunAdmissionContext.begin_dispatch()`；context 每次构造生成 `os.urandom(32)` nonce（不持久化、不打印、不进审计）；`_issued[id(token)] = token` 登记。
- **验证**：仅同一 `RunAdmissionContext.consume_dispatch(token, ...)`；接受条件（全部满足，任一失败 → 稳定 deny code，默认拒绝）：
  1. `isinstance(token, DispatchAdmissionToken)` 且 `self._issued.get(id(token)) is token`（JSON/dict/复制 dataclass 均拒绝 → `ADMISSION_TOKEN_UNKNOWN`）；
  2. 未消费过（`_consumed` 集合）→ 已消费 `ADMISSION_TOKEN_REPLAYED`；
  3. `token.run_id == identity.run_id` 且 `token.run_epoch == identity.run_epoch` → 否则 `RUN_EPOCH_MISMATCH`；
  4. `token.authorization_id == self.authorization_id` 且 `token.scope_id == self.scope_id`；
  5. `token.dispatch_ordinal == expected_next_ordinal`（严格递增、无回退/跳号）→ `ADMISSION_TOKEN_ORDER_INVALID`；
  6. `call_id/prepared_digest/payload_digest/payload_length` 与本次 attempt 的 prepared 值逐字段相等 → `ADMISSION_TOKEN_BINDING_MISMATCH`；
  7. `now < expires_utc`（token TTL ≤ `DISPATCH_TOKEN_TTL_SECONDS`，建议 30s，与 send capability 对齐；且不晚于 run deadline）→ `ADMISSION_TOKEN_EXPIRED`；
  8. `state == ACTIVE` 且未超 run deadline、`ordinal ≤ effective_max_calls` → `RUN_ADMISSION_INACTIVE` / `RUN_DEADLINE_EXCEEDED` / `RUN_BUDGET_CALLS_EXCEEDED`。
- **成功**：标记 token 已消费、`expected_next_ordinal += 1`；返回 `None`。
- **跨 Run 不可复用**：token 绑定 run_epoch + context 实例 registry；旧进程/旧 Run 的 token 在新 context 中必然 `ADMISSION_TOKEN_UNKNOWN` 或 `RUN_EPOCH_MISMATCH`；不同 Run 的 nonce 不同。
- **不在 token 中放 Key/原始请求**：只放摘要/标识符；`payload_digest` 是现有 provider request digest（哈希），非原始内容。

### 4.4 Controller 接入点（实现阶段）

- `TrustedController.__init__(..., run_admission: RunAdmissionContext | None = None)`（**默认 None = 冻结行为**）。
- `_handle_payload_serial`：在 `_prepare_checked` 成功、quota/identity 检查后、**`_broker_reserve()` 之前**：
  ```python
  if self.run_admission is not None:
      token = self.run_admission.begin_dispatch(...)          # 可抛 RunAdmissionDenied
      denial = self.run_admission.consume_dispatch(token, ...) # None 才继续
      if denial is not None:
          raise BridgeError(denial)   # 稳定 code；不 Reserve
  ```
- 若 run admission 未接线（`None`），行为与 `fd1d3a6` **逐字节一致**（现有 1420 测试不需改动）。
- `controller.main(..., run_admission=None)`：仅把对象传给 `TrustedController`；在 **start Broker 之前**校验 `context.state == ACTIVE` 且 `context.owner_pid == os.getpid()`（防止伪造/反序列化对象），否则稳定 exit（实现阶段定义 `RUN_ADMISSION_NOT_ACTIVE` 与退出码，建议格式与现有 `ERROR_*`/`EXIT_*` 一致，且不与其他退出码冲突）。
- 新增可选 config 字段 `run_admission: {...}`（trusted policy，strict no-extra）：仅当存在时 trusted entry 走 A2 路径；旧 policy 不提供 → 旧路径（默认不变，明确标注“未强制 run admission”）。

---

## 5. 审计设计

### 5.1 Run admission audit（新 JSONL；append-only）

文件：`run-admission.jsonl`（默认与 attempt DB 同目录，`default_run_admission_path(attempt_db)`；目录 0700，文件 0600，`O_APPEND|O_CREAT|O_NOFOLLOW|O_CLOEXEC`，每条 `fsync`，创建时目录 `fsync`；最多 4096 条/文件，超限 fail-closed `RUN_ADMISSION_AUDIT_FULL`）。

字段（**封闭 allowlist**；均为枚举/有界标识符/hex 摘要，无 Key/原始请求）：

```json
{
  "schema": "m0.g4r.run-admission.v1",
  "event": "intent | outcome | dispatch_denied | final",
  "utc": "2026-11-21T00:00:00Z",
  "launcher_instance_id": "<uuid4 hex>",
  "launcher_uid": 0,
  "run_id": "<from Admission>",
  "admission_id": "<from Admission>",
  "admission_sha256": "<64 hex>",
  "admission_nonce_sha256": "<64 hex（不写 nonce 原文）>",
  "authorization_id": "<identifier>",
  "approver": "<identifier>",
  "key_id": "<identifier>",
  "authorization_payload_sha256": "<64 hex: sha256(canonical(signed payload without signature))>",
  "run_epoch": "run-<32 hex>",
  "expected_bindings_sha256": "<64 hex>",
  "observed_bindings_sha256": "<64 hex>",
  "binding_checkpoint": "pre_start",
  "route_id": "<bounded>",
  "provider": "<bounded>",
  "model": "<bounded>",
  "tool_set_sha256": "<64 hex>",
  "tool_names": ["skill_lookup"],
  "budget_scope": "<bounded>",
  "authorization_max_calls": 50,
  "admission_max_calls": 8,
  "effective_max_calls": 8,
  "authorization_expires_utc": "...",
  "run_deadline_utc": "...",
  "decision": "ALLOW | DENY",
  "reject_reasons": ["AUTHORIZATION_REPLAYED"],
  "consumed": "YES | NO | UNKNOWN",
  "use_record_sha256": "<64 hex|null>",
  "use_log_durability": "KNOWN | UNKNOWN",
  "historical_holds_observed": 0,
  "historical_holds_modified": false,
  "external_network_calls": 0,
  "real_model_calls": 0,
  "provider_keys_seen": 0
}
```

写入时序（两阶段，保证 crash 可审计）：
1. 在 consume **之前**写 `event=intent`（decision 暂定 `PENDING`? 为避免与 schema 冲突用 `decision: "PENDING"` 或 event=intent 里省略 decision+consumed）；若 intent 写失败 → **不消费**，直接 deny exit（`RUN_ADMISSION_AUDIT_UNAVAILABLE`）。
2. consume 后写 `event=outcome`（ALLOW/DENY + consumed 三态 + record sha）。
3. 若 outcome 写失败：fail closed，**不启动 Broker**；stderr `RUN_ADMISSION_AUDIT_UNAVAILABLE`；由于消费可能已提交，run 必须人工对账（不自动重试）。
4. 进程正常结束写 `event=final`（状态/计数；写失败只计数不计错，但已在运行中的审计缺口要记录）。

**为什么 two-phase**：单条记录在“已消费但未写审计”的崩溃窗口会掩盖消费事实；intent 先落盘 + 确定性 run_epoch 让重启可推断“可能有消费”，配合 use log 的 REPLAYED 即可重建事实。评审若认为 two-phase 过重，可降级为“intent only + consume 后 best-effort outcome”，但需在报告声明残余风险。

### 5.2 不记录的内容（硬约束）

不在审计中记录：Key/Secret、DP 私钥/种子、原始 prompt/messages/tool 参数/文件内容、session 文本、真实 URL/凭据、宿主 home 路径、完整授权文件原文、签名原文（只记 payload digest）。`tool_names` 只允许已在受信 policy 白名单内的 name（≤16 个，每个 ≤64 字符）。

### 5.3 与既有 journal 的关系

| journal | 层级/所有者 | 本 ADR 变化 |
|---|---|---|
| `dispatch-window.jsonl` | Controller per-dispatch（G4-F2） | **附加字段**（不改变既有 `outcome/reserved/dispatched/settled/error_code` 语义）：`run_admission: {run_epoch, dispatch_ordinal, token_consumed, denial}`；无 run admission 时字段省略或 `null`（实现阶段保持既有 F2 测试断言通过） |
| `request-lifecycle.jsonl` | transport/request（G4-R R2） | **不改**；run admission 拒绝发生在 Controller 之前，由 run admission journal 记录；若 dispatch token 拒绝，可在现有 `failed_before_reserve` 事件的 `stage` 中加 `run_admission`（实现阶段评估，不强制） |
| `recovery-diagnostics.jsonl` | recovery（G4-R R2） | **不改**；run admission 路径不触发 recovery |
| Attempt DB / Reservation / Claim / Receipt | Controller/Broker（现有） | 拒绝路径 **0 新写入**；历史 hold 只读计数 |
| LiveGate / egress journal | 现有 | **不改** |

### 5.4 Dispatch audit 附加字段（实现阶段）

`dispatch-window` 记录增加（仅当 run admission 启用时）：
`run_epoch`, `run_id_sha256`（不写 run_id 原文？run_id 是受信标识符，可写；建议写原文 + admission_sha256）、`dispatch_ordinal`, `admission_token_consumed: bool`, `admission_token_sha256`（token 的字段摘要，不是 nonce）, `admission_denial: <code|null>`。
F2 既有测试断言的是字段子集/计数；实现阶段必须**先跑 F2 全套**并确认附加字段不破坏断言（设计阶段标记为验收项）。

---

## 6. 本轮 test-only / no-key Trusted Admission harness 设计

### 6.1 定位与边界

- **只增加测试专用/无 Key 的 Trusted Admission harness**：受保护临时签名/授权 fixture + Fake Broker + Fake Backend + 双 principal 布局。
- **系统 LiveGate 永远 BLOCKED**：harness 不触碰 `gates.py`、`run_live.sh`、CLI `--live`、Adapter；静态扫描新增代码无网络/Provider/Key env 读取。
- **不部署**人类签名根/Key Broker/Egress；`TEST_ONLY_` Ed25519 seed 只存在于测试进程/临时目录，绝不进入仓库、Candidate、Packet。
- 复用现有受信组件，不新建信任根：`load_execution_authorization` / `consume_execution_authorization` / `TrustedSendGate` / `BrokerClient`+Fake broker / `FakeBackend` / `AttemptJournal` / `Admission`。

### 6.2 目录与文件（实现阶段）

```text
src/autoteacher_m0/bridge/run_admission.py          # 新增 trusted-domain 模块（无 Key/网络）
src/autoteacher_m0/bridge/controller.py             # 可选参数 run_admission（默认 None 冻结行为）
scripts/g4/stage/trusted_entry_g4c.py               # 可选 --run-admission 模式（或新增 trusted_entry_a2.py）
tests/integration/g4r_admission/                    # 新测试包
  conftest.py
  admission_support.py                              # TEST_ONLY fixture：签名授权/keys/revocation/use-log/Admission
  test_run_admission_host.py                        # run-level 正负例
  test_dispatch_token.py                            # token 正负例
  test_run_admission_wiring.py                      # controller/trusted entry 接线（Fake Broker）
  test_run_admission_audit.py                       # 审计字段/不记录内容
scripts/g4/admission_probe.py                       # Reviewer 可独立运行的 probe（不 import owner test helpers）
artifacts/a-next/run-admission/<utc>-<sha>/         # gitignored 原始 JSONL/日志
```

### 6.3 Fixture 设计（受保护临时签名/授权）

- 复用 `tests/integration/g4_a/g4a_support.TrustedFixture`（`TEST_ONLY_SEED=bytes.fromhex("5a"*32)`；repo mirror + 外部 trusted 目录 + use log 0700；签名/授权文件 0600、非 symlink、仓库外）。引用：`tests/integration/g4_a/g4a_support.py:169`（`TrustedFixture`）、`:32`（`NOW`）、`:44`（`RUN_EPOCH`）。
- 授权模板：`base_payload(bindings)` + 唯一 `authorization_id` + 受控 issued/not_before/expires（NOW 附近）；**新增** run admission 场景所需：`allowed_tools=("skill_lookup",)`、预算/期限边界、5 root bindings 与 launcher policy 一致。
- keys/revocation 文件：测试临时目录、0600、外部；`TEST_ONLY_` key_id 明确前缀；**测试断言这些材料不进 stdout/日志/Packet**。
- Admission 文档：按 `admission.py` strict schema 生成（`admission_nonce` 32-hex、`launcher.uid=0`、`container=true`、`run_id`、limits、tool_schemas、expiry）；每个测试用新 nonce → 新 Run epoch。
- Fake Broker：复用 `tests/integration/g4_f3` 的 real-subprocess Fake Broker（Unix socket，无网络；`start_broker(tmp_path)`/fake config）与 `tests/integration/g4_f5/g4f5_support.py` 的 `start_controller` 布局；Fake Backend 用 `src/autoteacher_m0/bridge/fake_backend.py` 的 fixture script（`ok_usage/tool/stream/...`）。
- 双 principal：
  - **L1-HOST 变体**（本 PR 默认）：launcher/controller/ broker/fake 均为宿主受信进程（root），candidate 只作为协议请求生成器（不启动真实 DSH）；用 `expected_peer_uid`/`expected_uid` 现有语义模拟 principal 分离；
  - **L2 变体**（A-PR3/A4，不属于本 PR）：真实 DSH no-key + trusted container uid 0 + candidate uid 65534 + 独占 OCI 窗口（rootfs 可写副本，永不直挂冻结 rootfs）；本 ADR 只定义验收点，不执行。

### 6.4 故障注入（产生**真实** consume 码，不 mock 成功）

复用 A1/P2-03 已建立的 fixture 手法，而不是注入假 consumer：

- `DURABILITY_UNKNOWN`：patch `authorization_module.os.fsync` 在目录 fsync 处抛 `OSError`（参考 `tests/integration/g4r_auth/test_r1_atomic_use_record.py:352,490` 现有断言与 `scripts/g4r_review/r_rev2_race_probe.py` 的同名检查）；
- `WRITE_FAILED`：patch `os.link`/`os.open` 抛错；
- crash-before-link / crash-after-link：现有 crash hook/进程 fork（R1 已证明）；
- body-id mismatch（A1）：手工写合法 JSON 但 authorization_id 与文件名不符 → INVALID；
- 重放/epoch：预发布合法记录（用 fixture 先 consume 一次）→ 第二次 GET REPLAYED；用另一 Admission 的新 epoch → EPOCH_MISMATCH；
- token 负例：JSON dict、`dataclasses.replace` 复制、跨 context token、序号跳号、digest 不符、过期、超 max_calls。

### 6.5 不许新增 Live allow path（实现验收点）

- 新增代码 diff 静态扫描：无 `deepseek_harness`/`requests`/`httpx`/`urllib`/`socket.connect`/`subprocess curl`；无 `os.environ`/`getenv` 读取 Key-like 变量；无 `--live`/allow switch；`gates.py`/`run_live.sh`/`dsh_adapter.py`/`cli.py` 零 diff。
- harness 断言 `LiveGate().inspect(...).status == "BLOCKED"` 与 CLI `smoke --live` exit 3 仍成立（作为回归，不新增入口）。

---

## 7. 拒绝矩阵（设计目标；实现阶段逐行落测试）

**通用期望**：除表内明确注明的“既有 post-Reserve hold”外，每一行都必须满足 **0 新 Broker Reserve、0 Fake send、0 新 Attempt**；历史 hold **只读、不改写、不释放、不重结算**。 “Broker 未启动”= 在该拒绝路径中 BrokerClient 进程从未创建（结构性 0），比“启动了但没 Reserve”更强。

| # | 场景 | 检测层 / 检查点 | 稳定 reason（示例） | consume 结果 | Broker/Fake | Reserve | Fake | Attempt | 审计/证据 | 历史 hold |
|---|---|---|---|---|---|---|---|---|---|---|
| R-01 | 伪造签名 | load（`pre_start`） | `HUMAN_SIGNATURE_INVALID` | 未调用 | 未启动 | 0 | 0 | 0 | run audit DENY(consumed=NO) | 不变 |
| R-02 | 未注册/未知 key_id | load | `UNKNOWN_APPROVAL_KEY` | 未调用 | 未启动 | 0 | 0 | 0 | 同上 | 不变 |
| R-03 | 过期/未生效 | load 时间窗 | `AUTHORIZATION_NOT_CURRENT`(+EXPIRED/NOT_YET_VALID) | 未调用 | 未启动 | 0 | 0 | 0 | 同上 | 不变 |
| R-04 | authorization_id 在 revoked_ids | load 撤销 | `AUTHORIZATION_REVOKED` | 未调用 | 未启动 | 0 | 0 | 0 | 同上 | 不变 |
| R-05 | 同 Run 重试（同 epoch，已消费） | consume | `AUTHORIZATION_REPLAYED` | 失败（本 attempt 未消费） | 未启动 | 0 | 0 | 0 | DENY(consumed=NO, replay) | 不变 |
| R-06 | 另一 Run 复用同一授权（新 nonce→新 epoch） | consume | `AUTHORIZATION_EPOCH_MISMATCH` | 失败 | 未启动 | 0 | 0 | 0 | DENY(consumed=NO) | 不变 |
| R-07 | Use record body id 与文件名/期望不符（A1/P2-01） | `_read_use_record` | `AUTHORIZATION_USE_RECORD_INVALID`（**不得** REPLAYED） | 失败 | 未启动 | 0 | 0 | 0 | DENY(consumed=NO) | 不变 |
| R-08 | record 损坏/截断/多 key/非法 schema | `_read_use_record` | `AUTHORIZATION_USE_RECORD_INVALID` | 失败 | 未启动 | 0 | 0 | 0 | 同上 | 不变 |
| R-09 | record symlink/hardlink nlink>2/FIFO/group-writable | 读路径 lstat/fstat | `AUTHORIZATION_USE_RECORD_INVALID` / `UNREADABLE` | 失败 | 未启动 | 0 | 0 | 0 | 同上 | 不变 |
| R-10 | 并发 launcher 抢同一授权（2/10/50） | consume 原子 link | 恰 1 成功；其余 `AUTHORIZATION_REPLAYED` | 唯一 winner=YES，losers=NO | losers 未启动 | 0 | 0 | 0 | winner ALLOW + losers DENY | 不变 |
| R-11 | 写临时/链接失败（真实 OSError 注入） | consume | `AUTHORIZATION_USE_LOG_WRITE_FAILED` | 未消费（未发布） | 未启动 | 0 | 0 | 0 | DENY(consumed=NO)；operator 可重试 | 不变 |
| R-12 | crash-before-link | 进程崩溃 | （无记录） | 未消费 | 未启动 | 0 | 0 | 0 | intent-only（若已写审计） | 不变 |
| R-13 | 目录 fsync 失败 / crash-after-link-before-dirfsync | consume | `AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN` | **UNKNOWN（已花掉概率=100% 可见）** | 未启动 | 0 | 0 | 0 | DENY(consumed=UNKNOWN, durability=UNKNOWN)；run `BLOCKED_PENDING_RECONCILE`；同授权后续=REPLAYED | 不变 |
| R-14 | use log 满 / temp 超限 | consume | `AUTHORIZATION_USE_LOG_FULL` / `WRITE_FAILED` | 未消费 | 未启动 | 0 | 0 | 0 | DENY(consumed=NO) | 不变 |
| R-15 | 预算不一致/超限（auth vs admission vs policy） | run admission 启动检查 | `RUN_BUDGET_MISMATCH` / `RUN_BUDGET_CALLS_EXCEEDED` | 未调用或 token 拒绝 | 未启动/已启动但未 Reserve | 0 | 0 | 0 | DENY(consumed=NO) | 不变 |
| R-16 | Run 期限超限（启动时已过期） | run admission | `RUN_DEADLINE_EXCEEDED` | 未调用 | 未启动 | 0 | 0 | 0 | 同上 | 不变 |
| R-17 | 启动时 binding 漂移 | `binding_drift("pre_start")` | `BINDING_DRIFT:PRE_START:<reason>` | 未调用 | 未启动 | 0 | 0 | 0 | DENY(consumed=NO) | 不变 |
| R-18 | tool/schema 漂移（actual≠signed 或 schema digest≠policy） | run admission tool 检查 | `ADMISSION_TOOL_SCHEMA_MISMATCH` | 未调用 | 未启动 | 0 | 0 | 0 | DENY(consumed=NO) | 不变 |
| R-19 | 无 token / 候选 JSON / 复制 dataclass / 伪造对象 | dispatch token consume（pre-Reserve） | `ADMISSION_TOKEN_UNKNOWN` | 已消费（run 级 YES，dispatch 拒绝） | 已启动 | **0 新** | 0 | **0 新** | dispatch-window `admission_denial` | 不变 |
| R-20 | token 重放 / 另一 Run / 序号回退/跳号 / digest 不符 / 过期 | dispatch token consume | `ADMISSION_TOKEN_REPLAYED` / `RUN_EPOCH_MISMATCH` / `ADMISSION_TOKEN_ORDER_INVALID` / `ADMISSION_TOKEN_BINDING_MISMATCH` / `ADMISSION_TOKEN_EXPIRED` | 同上 | 已启动 | **0 新** | 0 | **0 新** | 同上 | 不变 |
| R-21 | token 通过但 Reserve 被拒（Broker 预算/冲突） | 现有 Broker | 现有 code（`BUDGET_DENIED`/`CLAIM_DENIED`） | run 级已消费；dispatch token 已花 | 已启动 | 0（拒绝） | 0 | 0（Reserve 失败不建 attempt） | 现有错误码 + run 审计 | 不变 |
| R-22 | **post-Reserve** 撤销/超时/取消（既有 F5 路径；非 run admission） | 现有 pre-dispatch/send gate | `REVOKED_PRE_SEND:*`/`DEADLINE_*`/`CANCELLED_*` | 不适用（run 已准入） | 已启动 | 已发生（历史） | 0 | 已有 attempt 转 `SETTLEMENT_UNCERTAIN` | 既有 journal/diagnostics；**不重写历史 hold** | **仅此行为既有 hold，明确不改写** |
| R-23 | 审计日志不可写/满 | run journal 写入 | `RUN_ADMISSION_AUDIT_UNAVAILABLE` / `FULL` | 失败 → fail-closed，不启动 Broker | 未启动（若在 consume 前探测失败）/已消费则 BLOCKED | 0 | 0 | 0 | stderr + run 状态 | 历史 hold 不变 |
| R-24 | 成功消费后 crash-before-Broker；重启同 Run | consume | `AUTHORIZATION_REPLAYED` | 失败（consumed=NO 本次） | 未启动 | 0 | 0 | 0 | DENY(replay) → 人工对账 | 不变 |
| R-25 | Admission 文档重放（同 admission_id 二次注册） | 现有 `register_admission` | `ADMISSION_REPLAYED`（稳定 exit 3/相应 code） | run admission 之前/之后均拒绝 | 未启动 | 0 | 0 | 0 | 现有行为 + run audit | 不变 |
| R-26 | 审批文件被改成 Markdown/自签 JSON/环境变量/`--live` | load 外部文件规则 + CLI | `EXTERNAL_AUTHORIZATION_INVALID:*` / `SECURITY_BLOCKED` | 未调用 | 未启动 | 0 | 0 | 0 | 既有 LiveGate/CLI 负例 | 不变 |

> 说明：“0 新 Attempt”指 run admission 拒绝路径不调用 `begin_attempt`；R-21/R-22 是既有链路失败，其 Attempt/Reservation 语义由现有代码与 Broker 权威决定（R-22 明确只保留既有 hold，不改写、不重发）。

**额外结构证据（实现阶段测试断言）**：

- launcher-deny 路径：Fake Broker 进程未创建（无 pid/socket）；`broker requests` 不可得时以“进程未启动”断言；此外 Attempt DB 文件不存在/0 行。
- dispatch-token-deny 路径：Broker 已启动，但 `snapshot()["requests"] == 0`、reservations 0、attempts 0、fake counter 0。
- 失败注入后同一授权重试：R-11/R-12 → 第二次可成功（未消费）；R-13 → 第二次 `REPLAYED`（已消费）；R-05/R-06/R-24 → 恒 REPLAYED/EPOCH_MISMATCH，永不再 Reserve。

---

## 8. 与 A1（P2-01 use-record body id）的接口契约与冲突点

### 8.1 A1 预期改动（设计引用，不在本 ADR 实现）

A1 负责：在 `_read_use_record` 中校验记录 **body 的 authorization_id** 是否与“当前 final path / 期望 authorization id”对应，而不是只校验 `run_epoch`；不匹配返回稳定 `AUTHORIZATION_USE_RECORD_INVALID`（**不得**误记为真实 replay）。A1 不得 fallback 到旧 `O_CREAT|O_EXCL` 直接写 final；路径/类型/权限/O_NOFOLLOW/nlink/fsync-dir 维持 fail-closed。

### 8.2 A2 依赖的稳定接口（契约）

| 契约 | 要求 |
|---|---|
| C-1 `consume_execution_authorization(...)` 公共签名/返回 | 保持 `AuthorizationUse(authorization_id, run_epoch, consumed_utc, record_path)`；A2 只调用它 |
| C-2 错误码稳定性 | `AUTHORIZATION_USE_RECORD_INVALID`（body id/path 不匹配、损坏）、`AUTHORIZATION_REPLAYED`（同 epoch 已发布）、`AUTHORIZATION_EPOCH_MISMATCH`（异 epoch）、`UNREADABLE`、`WRITE_FAILED`、`LOG_FULL`、`DURABILITY_UNKNOWN` 的**语义不因 A1 改变** |
| C-3 body id 校验失败分类 | **INVALID，不是 REPLAYED**（A2 的 §3.5 映射依赖：INVALID=无法证明/不可重试自动，不声称已消费） |
| C-4 run_epoch 语义 | `_read_use_record` 继续返回**记录中的 epoch**；epoch 比较保留在 `_replay_reason`；A1 **不得**在 reader 内引入“expected epoch 必须相等”而使合法 EPOCH_MISMATCH 变成 INVALID |
| C-5 record path 语义 | `record_path = use_log_dir / (sha256(authorization_id) + ".json")` 不变；A1 的 path↔body id 校验使用该确定性映射（A2 的失败归因/审计依赖 record_path 与 authorization_id 的绑定） |
| C-6 原子发布/目录 fsync/DURABILITY_UNKNOWN | 不变；A2 把 UNKNOWN 映射为“不发送 + 待对账”，不试图重试或清理 final |
| C-7 私有函数边界 | A2 **不** import `_read_use_record`/`_read_use_record_settled`；A1 可自由重构其内部签名（`expected_authorization_id` 参数），A2 不受影响 |

### 8.3 A1 建议的实现形态（供 Reviewer/Implementer 对齐，非本 ADR 实现）

```python
# authorization.py（A1 设计建议）
def _read_use_record(path: Path, *, expected_authorization_id: str) -> str:
    ...
    body_id = parsed.get("authorization_id")
    if (not isinstance(body_id, str) or not _IDENTIFIER.fullmatch(body_id)
            or sha256(body_id.encode("ascii")).hexdigest() + ".json" != path.name
            or body_id != expected_authorization_id):
        raise AuthorizationRejected(("AUTHORIZATION_USE_RECORD_INVALID",))
    ...
```
- `_read_use_record_settled(path, *, expected_authorization_id)` 同样透传；重试条件仅对 INVALID 且非 symlink（既有语义）。
- `consume` 在 load 成功后已持有 `authorization.authorization_id`，直接传入即可，**公共签名不变**。

### 8.4 冲突点与处置

| 冲突点 | 风险 | 处置 |
|---|---|---|
| A1 把 body-id 不匹配映射为 REPLAYED | A2 会把“被换记录”误判为已消费，审计语义错误 | 契约 C-3 明确 INVALID；A2 测试覆盖该行（R-07）；Reviewer 检查 A1 diff |
| A1 在 reader 增加“expected epoch”校验 | 合法跨 Run 重放（EPOCH_MISMATCH）退化为 INVALID，丢失证据 | 契约 C-4；A1 test 保留 EPOCH_MISMATCH 用例 |
| A1 修改 `_read_use_record_settled` 重试策略 | 与 A2 无直接耦合，但会影响 R-07/R-12 的时序断言 | A2 只断言最终码与“不再 Reserve”，不断言重试次数/耗时上限（允许 A1 调参） |
| A1/A2 并行修改同一文件（authorization.py vs controller.py/run_admission.py） | 合并冲突 | A1 只改 authorization.py；A2 新增 run_admission.py + controller.py 可选参数；两者不重叠；建议 A1 先合入并冻结，A2 rebase |
| A1 测试的 crash 注入与 A2 harness 共用 fixture | 重复/漂移 | A2 复用 `g4r_auth` 的 fixture 手法但不修改其文件；新增独立 `tests/integration/g4r_admission/` |
| Read-only `live_controller` 语义 | A2 不得让 inspect-only 路径产生消费 | run admission 只从 trusted entry/launcher 调用；`live_controller.py` 不改，仍无 consume/无发射 |

### 8.5 可测试性

- A1 与 A2 的测试可共享同一 `TrustedFixture`（签名/keys/revocation/use-log），但断言分层：
  - A1：记录 JSON body id ↔ 文件名/期望 id ↔ 分类码（纯模块级，无 Broker）；
  - A2：consume outcome → run admission outcome → 是否启动 Broker → 0 Reserve/0 Fake/0 Attempt → 审计行。
- 独立 Reviewer probe 建议独立实现“读 use log 目录 + 复算 record 名/body id + 消费分类”，不复用 Owner 测试 helper（参考 `scripts/g4r/r1_independent_probe.py` 模式）。

---

## 9. 测试计划（实现阶段执行；本 ADR 全部 `NOT_RUN`）

> 以下为计划，不是本轮结果。矩阵状态在实现阶段前保持 `NOT_RUN`，不得预填 PASS。

### 9.1 Host/L1（A-PR1 主交付）

| Test ID | 内容 | 断言 |
|---|---|---|
| A2-H01 | begin_run_admission 成功 | ALLOW、consumed=YES、use_record 存在、audit outcome、返回 ACTIVE context |
| A2-H02 | 伪造签名/未知 key/过期/未生效/撤销（参数化） | DENY + consumed=NO；**Broker 未启动**；0 reserve/fake/attempt |
| A2-H03 | 同 Run 重启（同 Admission/nonce） | consume REPLAYED → DENY(replay)；不启动 Broker；authorization 不被“二次使用” |
| A2-H04 | 另一 Run（新 nonce）复用同一授权 | EPOCH_MISMATCH → DENY；0 发送 |
| A2-H05 | 并发 2/10/50 launcher 抢同一授权 | 恰 1 ALLOW；其余 REPLAYED；仅 1 个 Broker 启动；无重复消费 |
| A2-H06 | 预算/期限不一致/超限 | RUN_BUDGET_MISMATCH/DEADLINE_EXCEEDED；0 Reserve |
| A2-H07 | binding 漂移/tool schema 漂移 | BINDING_DRIFT:PRE_START / ADMISSION_TOOL_SCHEMA_MISMATCH；0 Reserve |
| A2-H08 | consume 故障注入：WRITE_FAILED / DURABILITY_UNKNOWN / INVALID / UNREADABLE | 码映射；UNKNOWN→不发送+BLOCKED_PENDING_RECONCILE；WRITE_FAILED 后重试可成功；UNKNOWN 后重试 REPLAYED |
| A2-H09 | A1 body-id 场景（R-07；A1 合入后） | INVALID（非 REPLAYED）；0 发送；审计 consumed=NO |
| A2-H10 | dispatch token 正例：同一 Run 内 3 次合法 calls | 3 次 dispatch 全部成功（预算内）；仅 1 次授权消费；ordinal 1..3；0 REPLAYED 误判 |
| A2-H11 | token 负例：无/JSON/复制/跨 Run/重放/跳号/digest 错/过期/超 calls | 全部 pre-Reserve deny；0 新 Reserve/0 Fake/0 新 Attempt |
| A2-H12 | 审计字段 allowlist + 敏感内容扫描 | 无 Key/原始 prompt/tool args/session 文本；字段封闭枚举/hex；两阶段记录存在 |
| A2-H13 | 默认路径回归（run_admission=None） | `fd1d3a6` 既有行为不变：F2/F5/g4_a 相关套件通过；controller/trusted entry 旧模式逐字节等价 |
| A2-H14 | 静态边界 | 新增代码无网络/Provider/Key env import；`gates.py/run_live.sh/dsh_adapter.py/cli.py` 零 diff；LiveGate/CLI 负例仍 BLOCKED/exit3 |
| A2-H15 | 独立 probe | Reviewer 可运行 `scripts/g4/admission_probe.py` 在临时目录复算消费/拒绝/0 发送，不依赖 Owner 测试 helper |

### 9.2 L2（A-PR3/A4；本 PR 不执行）

- 真实 DSH no-key、双 principal、trusted container uid0 + candidate uid65534、`--network none`、rootfs 可写副本、独占窗口。
- Run 内 2 次合法调用（Echo + Tool）→ 1 次授权消费；重放/新 Run/撤销/pre-Reserve timeout/post-Reserve revoke 等 → 0 新 Reserve/0 Fake（既有 hold 例外只读保留）；记录 uid_map/peercred、request-lifecycle、dispatch-window、attempts、receipts、fake counter、run epoch。
- 本轮不执行、不填 PASS；保持 `NOT_RUN`。

### 9.3 证据布局（实现阶段）

```text
artifacts/a-next/run-admission/<utc>-<impl_sha>/
  argv.json / env.json（无 Key）
  run-admission.jsonl
  dispatch-window.jsonl / request-lifecycle.jsonl（引用）
  admission-negative/*.log（逐 R-xx）
  audit-index.json（case_id, command, utc, exit, status, raw_evidence, sha256, limitation）
```

---

## 10. 残余风险、开放问题与 Reviewer 关注点

### 10.1 残余风险（如实）

1. **本 ADR 未实现、未接线**：在实现合入前，P2-02 仍是开放 scope gap；不得以本文件声称任何“端到端强制”。
2. **旧模式不强制**：设计建议 run admission 通过 trusted policy 可选块启用，旧入口（无该块）行为不变。这意味着“未升级的部署仍无 run-level 强制”。实现阶段必须：在 trusted entry 中明确 `run_admission_required` 模式，并在报告/Packet 中声明“live 准入前必须启用此模式”；G4-H1 之前必须由人类/Reviewer 确认该模式为唯一生产路径。
3. **人类签名根/Key Broker/Egress 未部署**：即使 A2 接线完成，也只是 no-key/Fake harness 的强制消费；真实信任根仍缺失，Live 必须保持 BLOCKED。
4. **审计两阶段仍是 best-effort 边界**：outcome 写失败时“已消费但未记录 outcome”；以 intent + use log REPLAYED 可重建，但仍属残余，需要人工对账流程。
5. **run_epoch 依赖 Admission nonce 唯一性**：若维护者/Launcher 复用 Admission 文档（同 nonce）启动两次，第二次会以 REPLAYED 失败（fail-closed，安全）但可能造成运维困惑；Runbook 需写明“每个 Run 新 Admission”。
6. **L2 未验证**：本 ADR 的 0-Reserve/0-Fake 论证在 host 结构上成立；真实 DSH/容器/uid 场景需 A-PR3/A4 独占窗口验证。
7. **性能**：run 启动 +1 次目录 fsync/use record；每 dispatch +1 次 token 校验/in-memory 操作 + 审计（如实现 dispatch 级审计则 +fsync）。在 Fake 合成链中可接受，真实环境需测量。
8. **A1/A2 顺序依赖**：若 A1 的 body-id 校验语义与契约 C-3/C-4 不一致，A2 的拒绝矩阵会错误分类；需 Reviewer 同时审 A1 diff 与 A2 映射测试。
9. **测试故障注入 vs 真实 FS 故障**：`fsync`/`link` 注入覆盖逻辑分类，但不证明真实磁盘/文件系统故障（部署验证仍需人类/OS 级证据）。
10. **Run admission token 为 in-process**：Controller 崩溃后 token 全灭；重启必须重新走 run admission（同 Run → REPLAYED）→ 不允许自动恢复未完成 dispatch。这是有意的 fail-closed，但会降低可用性，需 Runbook 说明人工对账步骤。

### 10.2 开放问题（请 Reviewer 判定）

- **Q1**：run admission 是否必须成为 trusted entry 的**默认强制**（对旧测试/兼容性影响大），还是先“opt-in 模式 + 明确标注未强制”？推荐后者，但要求在 G4-H1 前把 opt-in 变为唯一生产路径。
- **Q2**：`run_epoch` 派生公式是否接受（`admission_id + admission_nonce + run_id` → SHA-256 前缀）？是否要绑定 `authorization_id`（当前不绑定；重放/跨 Run 分类由 consume 记录完成）。若绑定 authorization_id，同一 Run 换授权（不应发生）会变成新 epoch；是否更安全？
- **Q3**：dispatch token 的 mint 点放在 `_prepare_checked` 之后（推荐，可绑定 prepared_digest）还是更早的 transport 层？consume 点放在 `_broker_reserve` 之前（推荐）还是 pre-dispatch（会留下已 Reserve 的 hold，违背“0 Reserve”）？
- **Q4**：run admission 审计两阶段（intent+outcome）是否接受？还是单条 best-effort + 依赖 use log？
- **Q5**：是否需要在 run admission 本地执行授权 budget 的 `per_call_cap/total_cap` 校验（defense in depth），还是只做启动时一致性 + `max_calls`/deadline，金额完全交 Broker？
- **Q6**：A1 的 body-id 校验是否也应在**同 epoch replay** 分类前执行（推荐：先 path/body 校验，再 epoch 分类；否则 body 被换后可能先命中 REPLAYED）？此点需与 A1 Implementer 对齐顺序。
- **Q7**：A-PR1 验收是否包含 L2（handoff A2 第 5 点是 L2），还是按 PR 拆分由 A-PR3/A4 承担？建议 A-PR1 = host/L1 + harness，L2 在 A-PR3。

### 10.3 对 Reviewer 的最小判定请求

请判定本 ADR：

1. 是否维持 INV-R1..R8 与 §7 拒绝矩阵（尤其“任何未知/失败 → 0 Reserve/0 Fake/0 Attempt；历史 hold 只读”），**没有安全降级**；
2. run-level（而非 per-dispatch）消费语义与 run_epoch/call_id 分离是否可接受；
3. A1 接口契约 C-1..C-7（尤其 C-3/C-4）是否可执行；
4. harness 是否确实 test-only/no-key、无新增 Live allow path；
5. 是否允许进入实现阶段（A-PR1 实现 + 测试），以及 §10.2 的 Q1–Q7 取舍。

---

## 11. 实现阶段计划（仅当 Reviewer 判定后启动；本轮不执行）

1. **A1 先合入**（authorization.py body-id 校验）→ 冻结；A2 rebase。
2. 新增 `run_admission.py` + 单元测试（纯逻辑：epoch 派生、token 状态机、映射函数）。
3. `controller.main`/`TrustedController` 可选 `run_admission=None` 接线 + 默认路径回归（F2/F5/g4_a 全绿）。
4. trusted entry 可选 `--run-admission`（或新 entry 文件）→ 先做“启动前拒绝”路径（0 Broker），再打通成功路径。
5. `tests/integration/g4r_admission/` 主机负例 + Fake Broker 成功路径 + 审计测试 + 独立 probe。
6. docs：`docs/A_NEXT_AUTH_RUN_ADMISSION.md`（实现报告，owner 侧）+ evidence JSONL/矩阵更新（append-only）。
7. 之后 A-PR3/A4 做 L2 双 principal 真实 DSH Fake-only 取证。
8. 所有阶段保持 `LiveGate=BLOCKED`、0 Key/Provider/HTTP；Final Packet 由 A-PR4 另建新包。

---

## 附录 A — 证据命令（本轮实际执行）

```bash
cd "/root/Autonomous Teacher/worktrees/a-next-run-admission"
git rev-parse HEAD          # fd1d3a6d101f17e6a86d7c43f06c630326e3e3af
git log --oneline -6        # fd1d3a6 … d33e0aa … 1929af8 …
git diff --stat d33e0aa..HEAD -- src tests scripts
# → src/tests/scripts: 0 changes；仅 scripts/g4r_review/*（Reviewer 工具）

grep -rn "consume_execution_authorization" src --include=*.py
# → 仅 authorization.py:988 定义；0 生产调用方

grep -rn "load_execution_authorization\|require_execution_authorization" src --include=*.py
# → 仅 live_controller.py:29/132（inspect-only，永不 BLOCKED 打开、不消费）

grep -rn "dispatch_gate=" --include=*.py scripts src
# → scripts/g4/stage/trusted_entry_g4c.py（gate 构造后传入 controller.main）
# → src/autoteacher_m0/bridge/controller.py:2289（TrustedController 构造）

grep -n "def consume(self, authorization" src/autoteacher_m0/security/egress.py
# → 2210（per-dispatch send capability 消费点；不是 ExecutionAuthorization）
```

## 附录 B — 行号索引（基线 `fd1d3a6`）

| 引用 | 位置 |
|---|---|
| `ExecutionAuthorization` | `security/authorization.py:333` |
| `AuthorizationDecision` | `security/authorization.py:350` |
| `load_execution_authorization` | `security/authorization.py:478` |
| `require_execution_authorization` | `security/authorization.py:700` |
| `AuthorizationUse` | `security/authorization.py:795` |
| `_read_use_record` | `security/authorization.py:802` |
| `_read_use_record_settled` | `security/authorization.py:850` |
| `_replay_reason` | `security/authorization.py:872` |
| `_fsync_directory` | `security/authorization.py:918` |
| `_count_use_log_entries` | `security/authorization.py:942` |
| `consume_execution_authorization` | `security/authorization.py:988` |
| `DURABILITY_UNKNOWN` | `security/authorization.py:1095` |
| `TrustedSendGate.authorize` | `security/egress.py:1983` |
| `TrustedSendGate.consume` | `security/egress.py:2210` |
| Controller `_authorize_send` | `bridge/controller.py:751` |
| Controller send-cap consume | `bridge/controller.py:1153` |
| `controller.main` | `bridge/controller.py:2235` |
| `TrustedController(...)` in main | `bridge/controller.py:2285` |
| `Admission` / `load_admission` | `bridge/admission.py:47` / `:70` |
| trusted entry `main` / controller call | `scripts/g4/stage/trusted_entry_g4c.py:384` / `:458` |
| legacy trusted entry | `scripts/g3d/stage/trusted_entry.py:216` |
| inspect-only controller | `security/live_controller.py:132` |
| dispatch window journal path helper | `bridge/dispatch_audit.py:218` |
| request lifecycle path helper | `bridge/request_lifecycle.py:259` |
| recovery diagnostics path helper | `bridge/recovery_diagnostics.py:189` |
| P2-02 review record | `docs/REVIEW_G4R_INDEPENDENT.md:308` |
| R1 use-record tests | `tests/integration/g4r_auth/test_r1_atomic_use_record.py:39,117,352,368,490` |
| TEST_ONLY trusted fixture | `tests/integration/g4_a/g4a_support.py:169` |

---

**本文件结束。状态：`DESIGN_ONLY`；未实现、未运行新增测试、未改变任何安全状态常量；等待 Independent Reviewer 的“无安全降级”判定。**

## 附录 C — Errata / 行号基准（A2 实现后追加）

- **行号基准**：附录 A/B 中所有源码行号以**设计基线 `fd1d3a6`**（本 ADR 提交时的 worktree HEAD）为准。
  实现提交 `1f25552` 在 `bridge/controller.py` 插入 run admission 代码块后，`_handle_payload_serial`
  之后的行号（含原 `dispatch_gate.consume` 消费点、`controller.main`、`TrustedController(...)` 构造）
  相应后移若干行的偏移是预期的、仅行号偏移、不是语义变化。以后引用请以**符号/函数名 + `git show
  fd1d3a6:<path>`** 为准，或以当前实现文件重新 `grep -n`。
- **历史字符串更正**：附录 A 中 `scripts/g4/build_packet.py:311` 的
  `"authorization.py:816 consume_execution_authorization"` 是**冻结的历史 build_packet 字符串**
  （旧行号），不是当前源码行号证据；当前定义仍在 `security/authorization.py:988`
  （设计基线 `fd1d3a6` 与实现提交 `1f25552` 均未改该文件）。
- **设计门后已核对/修正的引用**（本 ADR 的 `960724b` 版本）：`AuthorizationUse` 793→795、
  `Admission` 46→47、`controller.main` 2237→2235；其余附录 B 行号已按 `fd1d3a6` 逐行核对。
- **实现阶段新增引用**：`bridge/run_admission.py` 为实现新增文件（无基线行号）；Controller 最小接线
  的语义证据见 `docs/A_NEXT_AUTH_RUN_ADMISSION.md` 的 C2–C8 映射章节。

- **Rebase 更新（A1 合入后）**：A2 实现已 rebase 到 A1 冻结分支 `fix/a-next-auth-record`
  （`e6f3aa6`，`authorization.py` net +51/−18，A1 所有）。重放后的提交链为
  `d7bbf3b`(ADR) → `07eccb9`(实现) → `6556967`(errata) → `ff44ef6`(R-25) → 报告 commit；
  原先引用的 `960724b`/`1f25552`/`e80bc8b`/`050411a` 是 rebase 前 SHA，仅作历史记录。
  A1 的 body-id 校验语义与本 ADR §8 契约 C-3/C-4 一致（INVALID 而非 REPLAYED），A2 未改
  `authorization.py`（相对 A1 分支 diff=0）。
