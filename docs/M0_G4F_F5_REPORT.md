# M0 G4-F5 — Revocation / Timeout / In-flight Failure（No-Key）

- **任务**：G4-F 指令 F5 —— 补齐 synthetic authorization 在 pre-reserve / post-reserve pre-send /
  post-send（在途）三个时机的撤销与检测；pre-send/post-send timeout；authorize→consume→send→receipt
  各窗口的 crash/kill/异常；以真实双 Principal、`--network none`、真实 DSH + Fake 取证，并给出
  **可停止 vs 只能保守** 的明确分类。
- **基线**：`0123884`（F1/F2/F3/F4 完成，工作区 clean 已核实）。
- **性质**：**no-key / no-model / no-external-network / no-live**。0 真实 Key、0 模型调用、
  0 外部 HTTP/TCP、0 真实计费；未执行 `podman pull`；全部 synthetic fixture；
  LiveGate 仍 `BLOCKED`，`M0 = DECISION_PENDING`。
- **明确不声明**：本文件不构成 G4 Full / E5-PreLive Full / G5 / G6 / Live 授权；
  不改变 `G4-H-01..06 = BLOCKED`；不声称真实 Provider 的远端 exactly-once/计费。

---

## 0. 结论摘要

| 项 | 结论 |
|---|---|
| 撤销时机 | 三时机全部覆盖：**pre-reserve 可停止**（0 ledger / Fake 0）；**post-reserve pre-send 不可发送**（reservation PENDING、attempt 保守、held>0）；**post-send 不可撤回**（仅 Broker 权威结算，不重发/不二次结算） |
| 撤销后新请求 | 拒绝于 **pre-reserve**（`ADMISSION_SELF_AUTH_DENIED`），不产生新 Reservation/Claim/Attempt/Fake；dispatch-window 记录 `rejected, reserved=false, dispatched=false` |
| 撤销输入 | 可信 launcher 拥有的 **root-owned synthetic revocation document**（`m0.g4c.revocation.v1`），gate 在 `pre_reserve` / `pre_dispatch` / `pre_send` 重读；**不是费用/发送权威**，不能 mint/settle/定价 |
| 失效姿态 | 已配置但缺失/非法/不可读 → **fail-closed**（`REVOCATION_STATE_INVALID`），不“当作未撤销” |
| pre-send deadline | 真实延迟 > deadline → **不 Reserve、不发送**（无 reservation/attempt/Fake） |
| post-send timeout | Fake 已收到字节（Fake=1、receipt 1）→ Attempt `SETTLEMENT_UNCERTAIN`、Broker `PENDING`、`held=reserved>0`、`known=0`；不重发、不 FREE |
| 在途失败窗口 | `after authorize before consume`、`after consume before Fake`、`after Fake receipt`、`after Attempt start`、`after authorize+consume` 的真实进程死亡/重放均保守；旧 Attempt 持久、无第二次发送、无第二次结算 |
| 可停止 vs 保守 | 见 §6：wire 前的 pre-reserve/pre-send 可拒绝；reservation 已创建或 wire 已跨越的只能保守（held/PENDING/UNCERTAIN），等待 Broker/证据 |
| 真实双主体 | 13 个 L2 case 全部在真实 trusted + Candidate 容器、`--network none`、canonical rootfs/deps 下运行；7 个 case 为真实 DSH，6 个为真实 Candidate hold-mode raw-UDS（crash 重放所需） |
| 证据 | 13/13 case PASS，**162/162 checks PASS**；`containers_after=[]`；`real_model_calls=0`、`real_external_http_calls=0`、`provider_keys_seen=0` |
| 回归 | 727 passed / 2 failed（g4_d D15 host-env + g3d frozen-src 已知项）；F5 host 12 passed；ruff 0.17.5 scoped PASS |

```text
G4-F5 = PASS_FOR_NO_KEY_REVOCATION_TIMEOUT_INFLIGHT_SCOPE
LiveGate = BLOCKED; G4-H = BLOCKED; M0 = DECISION_PENDING
```

---

## 1. 基线与提交链

| 对象 | 值 |
|---|---|
| 起点 | `0123884`（F1/F2/F3/F4 完成；clean） |
| 本包 feat | **`dbacb76`** `feat: G4-F5 revocation timeout and in-flight failure negatives (no-key)`；parent `0123884` |
| 本包 fix | **`c804bb8`** `fix: G4-F5 dsh recovery stop timing and deadline override (no-key)`；parent `dbacb76` |
| 证据运行 HEAD | `c804bb8` |
| G4-C stage | `stage-20261119T133157Z`；base/head `c804bb8`；manifest `3932e4499372…`；tree `2202ed40…`；trusted tree `1207d322…`；candidate tree `144e6cf7…` |
| rootfs / deps | `25491e45…` / `e07729d7…`（canonical） |

> fix 提交只改 `scripts/g4/{launch_c,run_g4_f5}.py`（recovery stop 时序、deadline override、
> marker 序列化），未改 `src/`。feat 提交包含全部 `src/` 与测试。未 amend / 未 push / 未 stage 他人文件。

---

## 2. 语义冻结：撤销输入、检查点与时点

### 2.1 撤销输入（synthetic authorization）

- 可信 launcher 生成一份 root-owned、`0600` 的撤销文档：
  `{"schema":"m0.g4c.revocation.v1","authorization_id","auth_epoch","revoked","revoked_utc","reason"}`。
- `TrustedSendGate` 新增可选 `authorization_id` / `revocation_path`；**未配置时行为与 F3/F4 逐字节一致**
  （F3/F4 回归证明）。
- 文档只回答“当前 synthetic run authorization 是否仍有效”；**不含**价格、token、reservation、capability、
  settlement，也不回写 Broker。它和 policy/admission 同处 root-owned state 信任边界，不是第二套费用权威。
- 严格校验：非 symlink、regular、≤64 KiB、字段集合精确、schema/epoch/ID 匹配；**已配置但缺失/不可读/非法
  → fail-closed**（`REVOCATION_STATE_INVALID`），避免“删掉撤销文件即可放行”。

### 2.2 检查点

| 检查点 | 代码位置 | 作用 |
|---|---|---|
| `pre_reserve` | `controller._handle_payload_serial`（`_prepare_checked` 之后、identity claim/Reserve 之前） | 撤销后**新请求拒绝**；0 reservation / 0 attempt / 0 Fake |
| `pre_dispatch` | `TrustedSendGate.authorize()`（mint 任何 capability 之前） | post-reserve pre-send 撤销：不 mint、不 hold、不发送 |
| `pre_send` | `TrustedSendGate.consume()`（进入 Fake 前最后可拒绝点） | 竞争窗口兜底；拒绝时**烧毁 capability**，之后清空撤销文件也不能复用 |

### 2.3 时点模型（与 F3 费用权威一致）

- **Broker 仍是唯一费用权威**；撤销只影响“能否发送/能否继续”，不改变 Broker 的 Reserve/Settle/Fail
  语义，也不改变 G3-C/D 账本状态机。
- 撤销导致 post-reserve 失败时：**不调用 settle/fail**（没有可靠 usage，不得伪造费用），
  reservation 保持 `PENDING`；恢复进程只读观察后 `held = reserved_cost > 0`。
- 撤销发生在 wire 之后：**不能撤回**；按实际 receipt/usage 正常结算（Broker `OK/FAILED` + cost），
  不重发、不二次结算；后续新请求在 `pre_reserve` 被拒。

---

## 3. 撤销矩阵（三时机）

| 时机 | 证据 case | 撤销被检测于 | wire | Fake | Broker | Attempt | 结果 |
|---|---|---|---|---:|---|---|---|
| (a) pre-reserve | `revocation-pre-reserve`（真实 DSH） | `pre_reserve` | 前 | **0** | **0 reservation** | 无 | `ADMISSION_SELF_AUTH_DENIED`，0/0/0，dispatch `rejected` |
| (b) post-reserve pre-send | `revocation-post-reserve`（真实 DSH） | `pre_dispatch`（authorize 拒绝） | 前 | **0** | **1 PENDING**，cost/reserved `0.002684`，spent 0 | 1，`SETTLEMENT_UNCERTAIN` | 不发送；恢复 gate `held=0.002684`、`known=0`；Broker PENDING |
| (b′) 同窗口 + 新请求 | `revocation-post-reserve-hold` | `pre_dispatch` → 第二次 `pre_reserve` | 前 | 0 | 1 PENDING | 1，uncertain | 第二次请求 `rejected`（reserved=false），reservation/claim/attempt/Fake 均不增加 |
| (c) post-send（在途） | `revocation-in-flight`（真实 DSH stream） | 在 receipt 之后写撤销；结算已无法撤回 | **后** | **1** | **1 OK**，cost `0.001022`，spent=committed | 1，`SETTLED` | 正常结算、无重发/双结算；gate `known=0.001022`、held=0 |
| (c′) 同场景 + 新请求 | `revocation-in-flight-hold` | 第二次 `pre_reserve` | 后 | 1 | 1 OK（仍 1 行） | 1，SETTLED | 第二次 `rejected`；Fake 仍 1；`dispatch-window` 两条（completed + rejected） |

**关键不变量**：
- 撤销后任何新请求都不产生新的 Reservation/Claim/Attempt/Fake；
- post-send 撤销不改变已发生结算（Broker 权威）；**无 Fee=0**；
- 同一 reservation 最多一次终态；`ALREADY_*` 不重复入账；
- `held>0` 只在 Broker 仍 `PENDING` 时存在；终态后 `held→0` 且 `known+=cost` 一次。

---

## 4. Timeout 矩阵

| 时机 | 证据 case | 机制 | Fake | Broker | Attempt | held/known |
|---|---|---|---:|---|---|---|
| pre-send deadline | `timeout-pre-send`（真实 DSH） | admission deadline `800ms`；test-only delay `2500ms` 在 `before_reserve` 前；真实 elapsed time 超时 | **0** | **0 reservation**，spent 0 | 无 | 0 / 0 |
| post-send timeout | `timeout-post-send`（真实 DSH stream） | Fake `stream_slow` receipt 先落盘并发出首 chunk，随后 2s stall；deadline `800ms` | **1** | **1 PENDING**，cost/reserved `0.002698`，spent 0 | 1，`SETTLEMENT_UNCERTAIN` | 停止前 `held=0.002698`、`known=0`；恢复进程仍 `held=0.002698`、`known=0`（保守） |

- **不自动重发**：`timeout-post-send` 的 `replay`/恢复路径没有第二次 Fake（Fake 恒 1）；
  `crash-*-hold` 与 `revocation-*-hold` 的 replay 均为 `ATTEMPT_ALREADY_STARTED` 或连接失败，账本不增。
- **绝不 FREE**：post-send timeout 的 `held` 等于 Broker `reserved_cost`，`known=0`；恢复后若按 receipt
  结算则 `known>0`、`held=0`；不存在“held=0 且 Broker PENDING”的路径。
- pre-send deadline 是 **stop** 类：没有 reservation、没有 attempt、没有 Fake；dispatch-window 记录缺失
  （见 §10 R7），账本/Fake 为空的证据来自 DSH error + DB 0 行。

---

## 5. In-flight failure 窗口矩阵

真实进程死亡使用现有 `G3B_TEST_MODE=1` + `G3B_CRASH_HOOK`（`os._exit(97)`）；新增两个 **同族 test-only**
窗口：`after_send_authorize_before_consume`、`after_send_consume_before_fake`（未新增生产后门；
不改变任何 allow/deny 判定，仅提前退出）。撤销/超时窗口使用 env-gated test-only delay
（`G3B_TEST_DELAY_HOOK/MS/MARKER`），只拉宽真实窗口，不跳过任何 checkpoint。

| 窗口 | 证据 case | Fake | Broker | Attempt | 恢复/replay |
|---|---|---:|---|---|---|
| after Attempt start, before authorize（既有 hook） | `crash-before-send`（hold） | 0 | 1 PENDING `0.001619` | 1 uncertain | recovery `held=0.001619`；replay 连接失败；无第二次发送 |
| after authorize, before consume（新增 hook） | `crash-after-authorize`（真实 DSH）+ `-hold` | 0 | 1 PENDING `0.002684` | 1 `SETTLEMENT_UNCERTAIN` | recovery `held=0.002684`、`known=0`；gate journal `AUTHORIZED` 1、`CONSUMED` 0；replay no-op |
| after consume, before Fake（新增 hook） | `crash-after-consume`（真实 DSH）+ `-hold` | 0 | 1 PENDING `0.002684` | 1 uncertain | recovery `held=0.002684`；gate journal `CONSUMED` 1；capability 烧毁不可复用 |
| after Fake receipt, before response（既有 hook） | `crash-after-receive`（hold） | 1 | 1 OK `0.001022` | 1 `SETTLED` | recovery 从 receipt/Broker 结算一次；Fake 仍 1；无重发/双结算 |

- `crash-after-authorize/consume` 的 DSH 变体证明：真实 Candidate 的请求在 wire 前被丢弃（DSH error），
  Fake 0、Broker PENDING、durable Attempt 保留；`-hold` 变体补充 replay no-op 检查。
- `crash-after-receive` 证明 wire 后的保守路径：receipt/usage 已持久化，恢复进程只从 Broker/receipt
  结算一次；`held→0`、`known=0.001022`，Fake 计数不变。
- 所有 crash case 的 `containers_after=[]`，恢复进程以 `ADMISSION_REPLAYED` exit 3（`admission_replayed_exit=true`）。

---

## 6. 可停止 vs 只能保守（冻结分类）

| 类别 | 时机 | 是否已产生 reservation/Attempt | wire | 处置 | 证据 |
|---|---|---|---|---|---|
| **STOPPABLE** | 撤销 pre-reserve | 否 / 否 | 前 | 直接拒绝；0 ledger、0 Fake | `revocation-pre-reserve` |
| **STOPPABLE** | deadline pre-reserve | 否 / 否 | 前 | 拒绝；0 ledger、0 Fake | `timeout-pre-send` |
| **CONSERVATIVE_ONLY** | 撤销 post-reserve pre-send | 是 / 是 | 前 | 不发送；reservation PENDING、attempt uncertain、held>0；等 Broker/证据 | `revocation-post-reserve(-hold)` |
| **CONSERVATIVE_ONLY** | 撤销 post-send | 是 / 是 | **后** | 不能撤回；按 Broker 终态结算；不重发/不二次结算；新请求拒绝 | `revocation-in-flight(-hold)` |
| **CONSERVATIVE_ONLY** | timeout post-send | 是 / 是 | **后** | attempt uncertain、Broker PENDING、held>0；不重发 | `timeout-post-send` |
| **CONSERVATIVE_ONLY** | crash after authorize/consume | 是 / 是 | 前 | 无 Fake；Broker PENDING；恢复 held>0；replay no-op | `crash-after-authorize/consume` |
| **CONSERVATIVE_ONLY** | crash after receipt | 是 / 是 | **后** | 只从 receipt/Broker 结算一次 | `crash-after-receive` |
| **CONSERVATIVE_ONLY** | crash after Attempt start | 是 / 是 | 前 | 恢复 uncertain、held>0；replay no-op | `crash-before-send` |

**判定规则（实现强制）**：
1. 未 Reserve 且未发送 → 可停止，且**不得创建** reservation/attempt/Fake。
2. 已 Reserve 但未跨 wire → 只能保守：**不 settle/fail**（无 usage），reservation 保持 PENDING，
   `held=reserved_cost>0`；恢复只读观察，不解锁发送。
3. 已跨 wire（Fake receipt 存在）→ 只能按 Broker 权威结算；撤销/超时/崩溃都不能撤回或重发。
4. 任何路径都不得 `Fee=0` / `FREE`；释放只能由 Broker 终态 + 合法 cost 触发一次。

---

## 7. 证据：13-case L2 矩阵（真实双 Principal）

运行：

```text
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/g4/run_g4_f5.py
```

结果：`ok=true`，13/13 case PASS，**162/162 checks PASS**；`utc 2026-11-19T13:32:32Z → 13:35:11Z`；
`containers_after=[]`；`real_model_calls=0`、`real_external_http_calls=0`、`provider_keys_seen=0`；
rootfs/deps canonical。

| case | 模式 | UTC | 检查 | Fake | Broker reservation | Attempt | held / known（恢复后） |
|---|---|---|---:|---:|---|---|---|
| `revocation-pre-reserve` | DSH | 13:32:32→39 | 9/9 | 0 | 0 | — | 0 / 0 |
| `revocation-post-reserve` | DSH | 13:32:39→52 | 14/14 | 0 | 1 PENDING `0.002684` | uncertain | **0.002684 / 0** |
| `revocation-in-flight` | DSH | 13:32:52→13:33:01 | 11/11 | 1 | 1 OK `0.001022` | SETTLED | 0 / **0.001022** |
| `timeout-pre-send` | DSH | 13:33:01→09 | 9/9 | 0 | 0 | — | 0 / 0 |
| `timeout-post-send` | DSH | 13:33:09→17 | 11/11 | 1 | 1 PENDING `0.002698` | uncertain | **0.002698 / 0** |
| `crash-after-authorize` | DSH | 13:33:17→24 | 11/11 | 0 | 1 PENDING `0.002684` | uncertain | **0.002684 / 0** |
| `crash-after-consume` | DSH | 13:33:24→31 | 11/11 | 0 | 1 PENDING `0.002684` | uncertain | **0.002684 / 0** |
| `crash-before-send` | hold | 13:33:31→46 | 12/12 | 0 | 1 PENDING `0.001619` | uncertain | **0.001619 / 0** |
| `crash-after-receive` | hold | 13:33:46→34:02 | 13/13 | 1 | 1 OK `0.001022` | SETTLED | 0 / **0.001022** |
| `revocation-post-reserve-hold` | hold | 13:34:02→23 | 18/18 | 0 | 1 PENDING `0.001619` | uncertain | **0.001619 / 0** |
| `revocation-in-flight-hold` | hold | 13:34:23→40 | 15/15 | 1 | 1 OK `0.001022` | SETTLED | 0 / **0.001022** |
| `crash-after-authorize-hold` | hold | 13:34:40→55 | 14/14 | 0 | 1 PENDING `0.001619` | uncertain | **0.001619 / 0** |
| `crash-after-consume-hold` | hold | 13:34:55→35:11 | 14/14 | 0 | 1 PENDING `0.001619` | uncertain | **0.001619 / 0** |

### 7.1 逐案要点

- **revocation-pre-reserve**：dispatch-window `outcome=rejected, error=ADMISSION_SELF_AUTH_DENIED,
  reserved=false, dispatched=false`；gate journal 有 `REVOCATION_CHECK pre_reserve
  RUN_AUTHORIZATION_REVOKED`；DB `reservations=0, claims=0, attempts=0, intents=0`，Fake 0；
  DSH `finish_reason=error`。
- **revocation-post-reserve**：dispatch-window `outcome=failed_after_reserve, reserved=true,
  dispatched=false`；gate journal `DENIED [RUN_AUTHORIZATION_REVOKED]`；recovery gate
  `held=0.002684, known=0`、`cost_view.reservation.broker_status=PENDING`；Fake 0。
- **revocation-in-flight**：receipt `utc_start=13:32:57`；`run/dsh-revocation.json` 记录
  `window=in_flight, observed=true, revoked=true`，写入发生在其后；dispatch-window
  `completed, reserved=true, dispatched=true, settled=true`；Broker OK `0.001022`、gate known 同额；
  DSH `finish_reason=completed, final_response="early"`。
- **timeout-pre-send**：admission `deadline_ms=800`；test delay 2500ms 在 `before_reserve` 前；
  DSH `finish_reason=error`；0 reservation/attempt/Fake；gate `sends_authorized=0`。
- **timeout-post-send**：dispatch-window `failed_after_reserve, reserved=true, dispatched=true,
  settled=false`；Fake 1 + receipt 1；before-recovery gate `held=0.002698, known=0`；恢复仍
  `held=0.002698, known=0`（Broker PENDING）；无第二次发送。
- **crash-after-authorize**：gate journal `AUTHORIZED 1, CONSUMED 0`；Fake 0；Broker PENDING；
  恢复 attempt `SETTLEMENT_UNCERTAIN, reason=NO_RECEIPT_AFTER_CRASH`，gate `held=0.002684`。
- **crash-after-consume**：gate journal `AUTHORIZED 1, CONSUMED 1`；Fake 0；Broker PENDING；
  恢复 `held=0.002684`；capability 已烧毁。
- **crash-after-receive**：Fake 1、receipt 1、Broker OK `0.001022`、attempt SETTLED；recovery 只结算一次。
- 两个 `-hold` 撤销 case：第二次请求 dispatch-window `rejected`，reservation/claim/attempt/Fake 均不增加；
  Fake 仍 1（in-flight）或 0（post-reserve）。

---

## 8. 真实双 Principal 证据

以 `revocation-pre-reserve` 为例（其余 case 同构，证据在各 `runs/<case>/`）：

| 项 | 观测 |
|---|---|
| trusted UID map | `0 100000 65536`（host uid 100000..） |
| candidate UID/GID map | `0 65534 1` / `0 65534 1` + `2000 2000 1` |
| trusted socket | `mode=0660 uid=0 gid=2000`，`setgid=false`，`type=socket` |
| peercred | trusted log `peer accepted uid=65534 gid=65534 pid=0`；`ready mode=0660 gid=2000 uid=0 peer_uid=65534` |
| mounts | `/project`/`/deps` ro；`/work/state`、`/work/g3b` rw；`/work` tmpfs `noexec,nosuid,nodev`；rootfs ro |
| network | `--network none`（两个容器）；无外部 socket |
| dispatch-window | `origin={kind:unix_peer, uid:65534, gid:65534, pid:0}`；tool `skill_lookup` 与 Admission approved digest 一致 |
| DSH | `0.2.2-rc.2` 真实 run；`traces/dsh-result.json`；无额外 provider 请求 |
| cleanup | `containers_after=[]`；`podman ps -a` 空；`rootfs_canonical=true`、`deps_canonical=true` |

> 13 个 case 全部是真实 trusted + Candidate 容器（7 个真实 DSH，6 个 hold-mode raw-UDS）。
> hold-mode 仅用于 crash 后 replay 需要保持 Candidate 存活的 case；它仍是真实 Candidate 容器、
> 真实 Controller/Broker/Fake/UID map/socket，不是 in-process mock。

---

## 9. Host 契约测试（可复现）

`tests/integration/g4_f5/`，12 passed（`-B`、无网络 conftest、真实 Broker/Fake 子进程）：

| 文件 | 覆盖 | 结果 |
|---|---|---|
| `test_f5_revocation.py` | 撤销文档严格性/fail-closed；pre-reserve 0 ledger；post-reserve deny + 新请求拒绝 + 恢复 held；consume 窗口烧毁 capability；post-send 不可撤回且新请求拒绝；非法文档 fail-closed | 6 passed |
| `test_f5_timeout.py` | pre-send deadline 无发送；post-send timeout uncertain+held+不重发；撤销+超时绝不 FREE | 3 passed |
| `test_f5_inflight.py` | after-authorize / after-consume 崩溃窗口持久状态与恢复；after-receipt 结算一次；replay no-op | 3 passed |
| 合计 | | **12 passed** |

证据：`artifacts/g4f/f5/host/{commands.jsonl,pytest.txt,junit.xml,summary.json}`。

---

## 10. 回归与静态检查

命令（`-B`、`PYTHONDONTWRITEBYTECODE=1`、deps 内 pinned pytest）：

```text
PYTHONPATH=src:artifacts/foundation/deps python3 -B -m pytest -q \
  tests/integration/g4_a tests/integration/g4_b tests/integration/g4_c \
  tests/integration/g4_d tests/integration/g4_f2 tests/integration/g4_f3 \
  tests/integration/g4_f5 tests/integration/g3c tests/integration/g3d \
  tests/integration/g3_bridge tests/unit/security/test_gates.py
```

| 套件 | 结果 |
|---|---|
| `g4_a` | 223 passed |
| `g4_b` | 38 passed |
| `g4_c` | 78 passed |
| `g4_d` | 25 passed / 1 failed（D15 host-only：`/root/.local/bin/python3.11` 在 0700 home 下，降权子进程不可穿越；用 `/opt/miniconda3/envs/quant/bin/python` 重跑 **1 passed**） |
| `g4_f2` | 30 passed |
| `g4_f3` | 23 passed |
| `g4_f5` | **12 passed** |
| `g3c` | 110 passed |
| `g3d` | 143 passed / 1 failed（`test_runner_does_not_modify_product_src`：frozen-src `git diff 4bd4803 -- src` 非空，G4 授权改码导致，历史报告已登记，**预期失败**） |
| `g3_bridge` | 31 passed |
| `gates` | 14 passed |
| **合计** | **727 passed / 2 failed / 729** |

- **ruff 0.17.5**（pinned，scoped）：
  `ruff check src/autoteacher_m0/{security/egress,bridge/controller}.py scripts/g4/{launch_c,lib_g4c,run_g4_f5}.py scripts/g4/probes/g4c_uds_probe.py scripts/g4/stage/trusted_entry_g4c.py tests/integration/g4_f5`
  → **All checks passed**。
- 全量 host 1285 项未重跑；本包按 F3/F2 的回归集合 + `g4_f5` 复跑并如实计数。

---

## 11. 残余与 UNVERIFIED

| ID | 残余 | 影响 / 处置 |
|---|---|---|
| **F5-R1** | post-reserve pre-send 的真实窗口只有微秒级；L2 用 env-gated test-only delay（`after_reserve_before_send`）拉宽 | 不是生产后门：`G3B_TEST_MODE=1` 且不跳过任何 checkpoint/判定；L1 用 gate wrapper 在 authorize 前写文档，完全不依赖 delay |
| **F5-R2** | 撤销文档由 root-owned state 提供，无独立签名/审计链 | 与 policy/admission 同信任边界；不是新权威；生产控制面输入的签名的/审计不在本轮范围 |
| **F5-R3** | 撤销文档被删除/恢复为 `revoked=false` 时，新的 `pre_reserve` 会再次放行 | 这是“撤销状态”的真实语义；已经 consume 的 capability 被烧毁，不会因 un-revoke 复活；没有历史回溯 |
| **F5-R4** | `timeout-pre-send` 的 `dispatch-window.jsonl` 记录缺失 | 流式 handler 在 test-only delay 阻塞 worker 时先发出 `DEADLINE_EXCEEDED` 并结束会话，worker 的 finally 未及落盘；账本 0 行/Fake 0/DSH error 仍可证。未为取证改动产品路径 |
| **F5-R5** | post-reserve/timeout 恢复时 `reconcile` 会以 `RECEIPT_DOCUMENT_SCHEMA_INVALID` 重写 attempt reason | 恢复仍为 `SETTLEMENT_UNCERTAIN`、held>0；原始 `RUN_AUTHORIZATION_REVOKED` 在 gate journal、`failed_after_reserve` 在 dispatch-window；无账本语义变化 |
| **F5-R6** | crash 使用现有 `os._exit(97)` hook，不是外部 SIGKILL | 与 G3-D/G4-C 既有 crash 证据同一机制；外部 SIGKILL 的时序窗口未单独枚举 |
| **F5-R7** | in-flight 撤销的时间顺序由“先观察到 receipt 再写文档”保证，UTC 秒级 | 因果证据（`observed=true` + receipt 存在 + 后续 settle）成立；未做纳秒级时序断言 |
| **F5-R8** | 未覆盖真实 Provider/真实计费/供应商侧撤销 | 与 G4-H-04 一致，仍 BLOCKED；全部为 synthetic fixture |
| **F5-R9** | 证据在 gitignored `artifacts/`，不随提交分发 | 与 F1-F4 一致；报告记录 argv/UTC/exit/DB/receipt/SHA/路径 |
| **F5-R10** | 未验证“撤销后 DSH 未来配置/动态注册永不发起请求” | 与本轮无关；F2 的 B03/E5-P04 结论不变 |

**明确 UNVERIFIED**：真实 Provider 的远端撤销/计费语义；生产控制面签名撤销链；外部 SIGKILL
在所有纳秒窗口的覆盖；G4 Full / E5-PreLive Full / G5-G6 / Live。

---

## 12. 范围与“不改”声明

**只改**：
- `src/autoteacher_m0/security/egress.py`：可选 `authorization_id`/`revocation_path`、
  `read_revocation_state`/`revocation_check`、`authorize`/`consume` 检查、snapshot `revocation`。
- `src/autoteacher_m0/bridge/controller.py`：`pre_reserve` 检查、撤销协议码映射（复用既有
  `ADMISSION_SELF_AUTH_DENIED`）、两个同族 test-only crash hook、test-only delay helper。
- `scripts/g4/{launch_c,lib_g4c,run_g4_f5}.py`、`scripts/g4/probes/g4c_uds_probe.py`、
  `scripts/g4/stage/trusted_entry_g4c.py`：stage policy 的 revocation 段、delay/撤销窗口、
  13-case runner 与检查。
- `tests/integration/g4_f5/`。

**未改**：`gates.py`、`scripts/run_live.sh`、`runtime/dsh_adapter.py`、DSH 核心、G3-B/G3-C/G3-D
协议帧/`ERROR_CODES`、Broker 协议 op、Reserve/Claim/Settle/Fail 语义、G3-C/D 账本状态机、
Admission/route/tool 白名单、历史测试/证据。**未新增**协议字段/错误码/Broker op；撤销复用
root-owned policy 侧输入，不进入 Broker。

---

## 13. 提交与 STOP

- `dbacb76`（feat；parent `0123884`）
- `c804bb8`（fix；parent `dbacb76`）
- docs 提交：本文件（parent `c804bb8`；不 amend / 不 push）

```text
G4-F5 = PASS_FOR_NO_KEY_REVOCATION_TIMEOUT_INFLIGHT_SCOPE
13/13 L2 cases, 162/162 checks
revocation: pre-reserve STOP / post-reserve STOP-BEFORE-WIRE / in-flight CONSERVE
timeout:    pre-send STOP / post-send UNCERTAIN + HELD
in-flight:  authorize/consume/receipt windows conserved; no double send/settlement
LiveGate = BLOCKED; G4-H = BLOCKED; M0 = DECISION_PENDING
```

**STOP.**
