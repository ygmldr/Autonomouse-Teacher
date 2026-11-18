# M0 G4-C — Trusted Synthetic Egress 实现与证据报告（No-Key）

- **任务**：G4-C-01..18（`docs/Autonomous_Teacher_M0_G4_PreLive_NoKey_Agent_Execution_Plan_v1.0.md` §6）
- **契约**：`docs/M0_G4_C_EGRESS_CONTRACT.md`（先冻结，再实现）
- **实现提交**：`3fd0d8569dd10f931231ee65a6a506b2f6c85577`，父 `795c263c06de1a4bbfde9392a6b32f3ab4f489be`
- **基线**：`795c263`（G4-A/B 完成，起点工作区 clean，已核实）
- **执行时间（UTC）**：2026-11-18T17:11Z → 18:12Z
- **性质**：**no-key / no-model / no-network / no-live**。0 真实 Key、0 模型调用、0 外部 HTTP/TCP、0 真实计费；
  未执行 `podman pull`；`--network none`；9 次真实双 Principal 容器运行全部 PASS；结束后容器为空。
- **本轮裁定**：**`PASS_FOR_G4_C_NO_KEY_SYNTHETIC_EGRESS_SCOPE`**（限定 synthetic fixture route）。
- **明确不声明**：real provider route、真实 TLS/DNS/计费、E5-PreLive Full、G4 PASS、G5/G6 可启动。
- **状态不变**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING`。

---

## 0. 裁定摘要

| 项 | 结果 |
|---|---|
| 契约 | `ProviderRouteContract` + `TrustedSendAuthorization` 冻结；synthetic 唯一 ACTIVE，real route 模板恒 BLOCKED |
| 实现 | `security/egress.py`（+≈820 行 additive contract/gate）、`bridge/controller.py`（+62/−7，可选 `dispatch_gate`，默认 `None` 时 G3-C/D 不变） |
| 唯一发送路径 | 门开启时，`TrustedSendGate.authorize()` → `consume()` → `TrustedEgressTransport.dispatch()` → Fake；任何失败 Fake=0 |
| pre_dispatch | 每次发送前执行 G4-A `binding_drift("pre_dispatch", approved, observed)`；15 组件闭包，容器内复算 `src/**`+`fake/**`，其余 Launcher 声明；缺失/异常 fail-closed |
| 真实双 Principal | 9 次容器运行：C01 Echo、C02 Tool、C18 Stream、negatives、replay、crash×2、broker-down、quota；**全部 PASS** |
| C01 | 1 Reservation/Claim/Attempt(SETTLED)/Receipt/Settlement；Fake=1；DSH usage == receipt usage；gate 1/1；0 live |
| C02 | 2 套独立账本/回执；distinct call_id；两组 Prepared=Claim、Payload=Receipt；Fake=2；skill_lookup 结果进入第二请求 |
| 负例 | 无 Claim（Broker kill）Fake=0；已消费 Claim 重放 `ATTEMPT_ALREADY_STARTED` Fake 不变；Prepared/Payload 变更 Fake=0 |
| 崩溃 | ATTEMPT 后发送前 crash：Attempt 持久、Fake=0、恢复启动 exit 3、重放 ECONNREFUSED；Fake 收到后 crash：Receipt 1、保守恢复、无第二次发送 |
| 证据 | `artifacts/g4/c/`（每 run 独立 argv/UTC/exit/uid_map/mountinfo/peercred/socket/DB/receipt/counter/checks/journal/digest pairs）+ `commands.jsonl`（245 行）+ `cases.json` |
| 回归 | G4-C host 78 passed；必跑集合 **637 passed / 1 known-failed**（G3-D 冻结 `test_runner_does_not_modify_product_src`，如实登记） |
| 真实计数 | `real_provider_calls=0`、`real_external_http_calls=0`、`provider_keys_seen=0`、`billable_send_allowed=0`、`live_gate=BLOCKED`、`run_live_exit=3` |

---

## 1. 改动面

### 1.1 产品代码（最小 additive）

| 文件 | 改动 |
|---|---|
| `src/autoteacher_m0/security/egress.py` | G4-C 契约与门：`ProviderRouteContract`（strict mapping loader）、`SYNTHETIC_ROUTE_CONTRACT`/`REAL_ROUTE_TEMPLATE`、`SyntheticSendBudget`、`TrustedSendAuthorization`（无 JSON 构造入口）、`TrustedSendGate.authorize/consume/pre_dispatch_binding_reasons/snapshot`、`tool_schema_digest`、`_strict_payload_document`；`record_outcome` 对任意非 None `error_kind` 保守为 `BILLABLE_UNKNOWN`（避免冲突 usage 被误判成功） |
| `src/autoteacher_m0/bridge/controller.py` | `TrustedController(dispatch_gate=None)`；`_authorize_send()`；provider 闭包内在 `_invoke_fake()` 之前 `consume()`；`main(..., dispatch_gate=None)` 透传。门为 `None` 时 G3-C/D 行为与 795c263 一致 |
| 未改 | `gates.py`、`scripts/run_live.sh`、`runtime/dsh_adapter.py`、`cli.py`、G3-C/D 协议/账本状态机、DSH 核心、历史证据/Packet |

### 1.2 测试与证据工具（新增）

| 路径 | 内容 |
|---|---|
| `tests/integration/g4_c/` | 78 个 host 测试：契约、授权绑定/一次性/过期/epoch、claim/permission 绑定、payload 变更、预算软硬阈值、pre_dispatch drift/incomplete/error、transport 无 permission/无 claim/重放、429/5xx/timeout/EOF/usage、controller 接线、静态无第二发送路径、LiveGate/run_live 不变、business-identity 重放 |
| `scripts/g4/build_stage_c.py` | G4 专用 stage builder：进程内重绑定 `lib_g3d.PRODUCT_BASE/G3D_ROOT` 后调用 G3-D 组装代码，`base_sha=head_at_build=G4 实现提交`；产物 `artifacts/g4/c/stages/stage-20261118T174947Z` |
| `scripts/g4/launch_c.py` | G4 专用 launcher：preflight 绑定 G4 HEAD；trusted 入口 `/g4c/trusted_entry.py`（run-dir 副本）；支持 hold/raw-UDS、restart-recovery、kill-broker、quota max_calls override |
| `scripts/g4/stage/trusted_entry_g4c.py` | trusted 容器入口：17 模块实际加载身份、G4-C policy/闭包重算、`pre_start` drift 拒绝、`TrustedSendGate` 接线、退出时写 egress snapshot |
| `scripts/g4/probes/g4c_uds_probe.py` | Candidate 侧真实 UDS/网络探针（negatives/valid/replay/over_quota/network） |
| `scripts/g4/run_g4_c.py` | 9 个 case 顺序编排、独立 evidence dir、容器/rootfs/deps 复核 |

---

## 2. 真实双 Principal 执行（L2）

### 2.1 运行矩阵

| Case | 场景 | 结果 | 关键计数 |
|---|---|---|---|
| c01 | 真实 DSH Echo | **PASS**（18/18 checks） | 1 Reservation OK / 1 Claim / 1 Attempt SETTLED / 1 Receipt / Fake=1 / gate 1±0 / usage 11+5 |
| c02 | 真实 DSH Tool 两轮 | **PASS**（20/20） | 2 Reservation OK / 2 Claim / 2 Attempt SETTLED / 2 Receipt / Fake=2 / gate 2±0 / distinct call_id |
| c18 | 真实 DSH Stream（stream_slow） | **PASS** | 1 ledger set / Fake=1 / `first_chunk_flushed` < `exit_after_finish` 同进程 monotonic |
| negatives | 8 个 UDS 负例 + 网络探针 | **PASS** | 全部 error；ledger 0；Fake=0；AF_INET EACCES、DNS EAI_AGAIN、无默认路由 |
| replay | valid + byte-identical replay | **PASS** | 第一次 finish/Fake=1；重放 `ATTEMPT_ALREADY_STARTED`/Fake 仍 1；1 authorization |
| crash-before-send | `after_attempt_start_before_fake_send` | **PASS** | Attempt=1 持久；Fake=0；恢复启动 exit 3；重放 ECONNREFUSED、Fake 0 |
| crash-after-receive | `after_fake_receive_before_response` | **PASS** | Receipt=1；Fake=1；恢复 exit 3；重放拒绝、无第二次发送/结算 |
| broker-down | trusted Broker SIGKILL | **PASS** | `BROKER_ERROR`；Fake=0；Attempt=0；gate 0 |
| quota | admission `max_calls=1` | **PASS** | 第一请求 finish/Fake=1；第二 `BUDGET_DENIED`；Fake 不变 |

每次 run 独立目录：`artifacts/g4/c/runs/<case>-<UTC>/`
（`env/`、`uid-map/`、`mountinfo/`、`socket-stat/`、`peercred/`、`db/`、`receipt/`、`traces/`、`run/`、`cleanup/`、`checks/`、`summary.json`、`runner.json`、`commands.jsonl`）。

### 2.2 C01/C02 账本与两对 Digest（实测）

```text
C01  call-cc8de3d3…  prepared=a29f84d7a5b5  claim=a29f84d7a5b5  payload=8ea503367cb5  receipt=8ea503367cb5
     prepared != payload（两个不同摘要，分别映射）
     reservation 9b654c5a… status=OK cost=0.001022；usage {input 11, output 5, total 18}
C02  call-30e8b383…  prepared=044cd7d75d27  claim=044cd7d75d27  payload=d13df0cb916d  receipt=d13df0cb916d
     call-f198f95b…  prepared=e0a2dca0bcbe  claim=e0a2dca0bcbe  payload=7868da9e0e76  receipt=7868da9e0e76
     reservation 9eaeb2f8… / 5dc9358b… 均 OK；Fake counter=2；gate AUTHORIZED=2 CONSUMED=2
```

- DSH 侧 usage（`traces/dsh-result.json` 的 assistant message）逐条等于对应 receipt usage；
- 第二请求的 tool result 来自第一轮 `skill_lookup`（`event_summary.tool_results` ≥ 1）；
- 两个 `call_id` 不同，Attempt/Claim/Receipt 按 call_id/receipt_id 独立配对。

### 2.3 负例 0 发送证据

- `negatives`：8 个请求全部 `terminal=error`，Reservation/Claim/Attempt/Receipt 均为 0，`received-count.json` 不存在 → Fake 0；
- `broker-down`：Broker 进程被 SIGKILL 后请求返回 `BROKER_ERROR`，无 Attempt，无 gate authorization；
- `replay`：第二次请求在 `claim_request_identity` 处 `ATTEMPT_ALREADY_STARTED`，Fake 计数保持 1；
- `crash-before-send`：`gate_no_authorization_before_crash`（AUTHORIZED=0）+ Fake=0；恢复后重放连接被拒绝；
- `crash-after-receive`：Fake=1、Receipt=1，恢复后重放不增加 Fake/Receipt/Reservation。

---

## 3. pre_dispatch 接线（G4-A → G4-C）

1. Launcher 启动前从**工作树 + stage manifest** 计算 15 组件闭包 → `ExpectedBindings`（5 roots），写入 root-only `/work/state/g4c-policy.json`；
2. trusted 容器内 `trusted_entry_g4c.py`：
   - 重算 12 个 repo 组件中容器可见的 `src/**`、`fake/**` 文件，其余使用 policy 的 `declared` sha；
   - external 三组件以 canonical `EXTERNAL.json`（含 runtime/deps/stage 原始 canonical hash）表示；
   - 启动时 `binding_drift("pre_start", approved, observed)`，任何 drift → 拒绝启动；
   - 构造 `TrustedSendGate(binding_approved=…, binding_observer=recompute, binding_checkpoint="pre_dispatch")`；
3. `authorize()` 在**每次发送前**调用 `binding_drift("pre_dispatch")`；缺失任一 hook → `PRE_DISPATCH_CHECK_INCOMPLETE`；observer 异常 → `PRE_DISPATCH_CHECK_ERROR`；drift → `BINDING_DRIFT:PRE_DISPATCH:<ROOT>_MISMATCH`；
4. 证据：`traces/g4c-binding-start.json`（approved/observed 两套 5 roots）+ 每次 `authorize` 的 journal 行；
5. 限制：容器内只能独立复算 `src/**`/`fake/**`；`config/`、`plugins/`、锁文件由 Launcher 声明；OS 级不可变仍属 G4-H。

---

## 4. G4 专用 stage/launcher 偏差（不修改 G3-D）

- G3-D 冻结 launcher 要求 `git diff cf40c6b -- src` 为空；G4-A/C 授权改码使该断言必然失败。
- G4-C 不修改 `scripts/g3d/**`、不改历史测试/证据、不改 G3-D matrix；新增 `scripts/g4/{build_stage_c,launch_c,run_g4_c}.py` 与 G4 trusted entry。
- stage：`base_sha = head_at_build = 3fd0d85`（G4 实现提交），manifest `d6495112…`，trusted/candidate tree `95b1b26…`；G3-D 冻结 stage `e1ff1449…` 保持原样。
- launcher：preflight base=G4 HEAD；trusted 命令 `/g4c/trusted_entry.py`；新增 `/g4c` ro 挂载；其余 UID/mount/`--network none`/清理参数复用 `lib_g3d`。
- **G3-D 冻结证据不变**：`artifacts/g3d/**`、`docs/M0_G3D_*`、G3 矩阵未改；新证据不得冒充 G3-D。

---

## 5. 测试与回归

| 项 | 命令 | 结果 | exit |
|---|---|---|---|
| G4-C host | `pytest -q tests/integration/g4_c` | **78 passed / 0 failed** | 0 |
| 必跑集合 | `pytest -q tests/integration/g4_a tests/integration/g4_b tests/integration/g4_c tests/integration/g3c tests/integration/g3_bridge tests/unit/security/test_gates.py tests/integration/g3d` | **637 passed, 1 failed**（G3-D 冻结断言） | 1 |
| 已知失败归因 | `tests/integration/g3d/test_d3_contract.py::test_runner_does_not_modify_product_src` | 断言 `git diff 4bd4803 -- src` 为空；G4-A/C 授权改码后必然失败；不改历史测试 | — |
| ruff | `ruff check --no-cache src/autoteacher_m0/security/egress.py src/autoteacher_m0/bridge/controller.py tests/integration/g4_c scripts/g4/` | **All checks passed** | 0 |
| stage 构建 | `python3.11 -B scripts/g4/build_stage_c.py` | exit 0；manifest `d6495112…`；rootfs/deps canonical | 0 |
| 容器套件 | `python3.11 -B scripts/g4/run_g4_c.py` | **9/9 PASS**；containers empty；rootfs/deps/stage 未漂移 | 0 |

---

## 6. 证据索引（`artifacts/g4/c/`，gitignored）

| 证据 | 路径 |
|---|---|
| 汇总 | `summary.json`（runner）、`cases.json`（C-case→checks/ledger/gate）、`commands.jsonl`（245 行） |
| stage | `stage-summary.json`、`stages/stage-20261118T174947Z/`、`logs/build-stage.log` |
| 每 run | `runs/<case>-<UTC>/{summary.json,runner.json,checks/checks.json,checks/gate-journal.json,db/snapshot.json,receipt/,traces/,run/,peercred/,uid-map/,mountinfo/,socket-stat/,cleanup/}` |
| 关键 run | `c01-*`、`c02-*`、`c18-*`、`negatives-*`、`replay-*`、`crash-before-send-*`、`crash-after-receive-*`、`broker-down-*`、`quota-*` |
| 回归/静态 | `logs/regression-host.log`、`logs/ruff.log` |

---

## 7. 残余与未主张

| ID | 残余 |
|---|---|
| R1 | C04/C05/C10/C11/C14(软硬阈值)/C15/C16 的决定性断言只在 L1-HOST；L2 fault injection 无法由 Candidate 远程触发，未新增产品测试钩子（矩阵标 PARTIAL） |
| R2 | 容器内只复算 `src/**`/`fake/**` 闭包；config/plugins/lock 由 Launcher 声明 |
| R3 | `authorize` 与 `transport.dispatch` 之间仍有 Python 内存窗口；由 consume 时重算字节 SHA 收窄，非 OS 级保证 |
| R4 | G4-C 只验证 synthetic fixture route；真实 route/TLS/DNS/proxy/redirect/计费未证明 |
| R5 | Broker hang/timeout 由既有 30s deadline 兜底，未单独做 hang 注入；Broker stop 已 L2 |
| R6 | C16 无 G4-C 真实 DSH resume 运行，引用 G3-D D2-11 L2 证据（同一 session 机制） |
| R7 | G3-D 冻结断言因授权改码必然失败；G4-E 应以 `--deselect` 取信号并保留本条 |
| R8 | 价格 3.00/10.00 是工程硬顶；synthetic 费率不是供应商真实价格；供应商硬额度需 G4-H 核验 |
| R9 | `g4c-policy.json`/journal 位于 `/work/state`（root 0700），不是独立签名账本 |
| R10 | 本轮 0 Key/模型/外网/Live；`run_live.sh` exit 3、`LiveGate=BLOCKED`、CLI/Adapter 未改 |

**未主张**：real route 可用、真实计费可控、供应商硬上限、E5-PreLive Full、G4 PASS、G5/G6 可启动、人类授权已部署。

---

## 8. STOP

- G4-C 完成后 **STOP**，不进入 G4-D；不触发 G5/G6。
- 本报告不构成授权、不替代独立 Reviewer、不代表维护者签收任何 P2。
