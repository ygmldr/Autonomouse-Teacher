# M0 G4-R R2 — P2-05 观察层分离 + P2-06 recovery first_cause（No-Key）

- **任务**：G4-R 执行计划 §5（R2）——P2-05 timeout 观察缺口与 P2-06 recovery 原因覆盖；
  对应矩阵 `R2-01..R2-09`。
- **PR/分支**：`fix/g4r-recovery-audit`（PR-R2），实施者 `a-g4r-recovery`（F-B）。
- **Parent SHA**：`3e7afee077845a071cd364e93ab209cac20b2d5f`（main，与计划基线一致）。
- **实现提交**：`4d59f22d6189a4d4805bc453b3bee56bc1e15528`
  `fix: G4-R P2-05 request lifecycle journal and P2-06 recovery diagnostics (no-key)`。
- **测试/证据脚本提交**：`7bd7fa2e8f5a05f0a63a0077905d0895c79d988a`
  `test: G4-R R2-01..R2-09 request lifecycle and recovery semantics (no-key)`。
- **Head（本报告提交）**：见 `git log -1`（文档提交在 impl/test 之后）。
- **性质**：no-key / no-model / no-external-network / no-live；0 真实 Key、0 模型调用、
  0 外部 HTTP/TCP、0 真实计费；Fake 均为 synthetic fixture；LiveGate 仍 `BLOCKED`，
  G4-H `NOT_AUTHORIZED`，G5 `BLOCKED`，M0 `DECISION_PENDING`。
- **证据等级**：本轮实测为 **L1-HOST**（真实 in-process Controller + 真实本地
  Broker/Fake 子进程或受控 stub Broker）。**L2-REAL-DSH 未执行**
  （`BLOCKED_NEEDS_ENVIRONMENT / UNVERIFIED`，见 §8），不把宿主结果冒充 L2。
- **不改**：Broker 费用权威语义、`gates.py`、LiveGate、冻结 Packet、旧 Reviewer 报告、
  其它 worktree；未 push/merge。旧 `docs/M0_G4F_F5_REPORT.md` 与
  `docs/REVIEW_G4F_INDEPENDENT.md` 一字节未改。

```text
G4-R R2 (P2-05/P2-06) = PASS_FOR_L1_HOST_NO_KEY_SCOPE
R2-01..R2-09 L1-HOST = PASS；L2-REAL-DSH = UNVERIFIED（未重建 Stage/未运行容器）
```

---

## 0. 结论摘要

| 项 | 结论 |
|---|---|
| P2-05 根因 | 先用真实时间线证明：`timeout-pre-send`（admission `800 ms`、test-only delay `2500 ms` 在 `before_reserve`）的 deadline 由 **transport/stream 层**在 worker 仍阻塞于 `before_reserve` 时观察到并结束会话；worker 的 `finally` dispatch 记录当时**确实还不存在**（复现 F5-R4）。请求层新 journal 在同一瞬间已有 `deadline_before_controller` 行，且如实记录 `controller_entered=true`、`stage=before_reserve`。 |
| 两层分离 | 新增 **请求级** `request-lifecycle.jsonl`（transport/请求层，`dispatch_seq` 仅在真实进入 dispatch handler 后出现，其余为 `null`），与既有 **Controller dispatch 层** `dispatch-window.jsonl` 概念分离；未进入 Controller 的 case 不再消耗/伪造 `dispatch_seq`（F2 兼容 rejection 行保留但 `dispatch_seq:null`、`controller_entered:false`、`request_level_only:true`、`reserved/dispatched/settled=false`）。 |
| P2-06 修复 | `first_cause` 与 `reconciliation_observation` 分离：只有旧 Attempt `reason` 属于已证枚举（`RUN_AUTHORIZATION_REVOKED` / `REVOKED_PRE_SEND:…`）**且** Broker 仍 `PENDING` 时保留 primary cause；每次 reconcile 决策追加独立 append-only `recovery-diagnostics.jsonl`（含 observation / Broker 状态 / action）。Broker `OK/FAILED` 仍是权威；每 reservation 仍至多一次 settle/fail；`PENDING/UNCERTAIN` 仍 held>0，不盲重发。 |
| 观测失败 | journal 写失败只增加计数并输出 `observability_status().observability_gap=true`；`safety_admission_changed=false`，安全准入/Reserve/Claim/Fake/settlement 判定不变（含真实 `/dev/full` ENOSPC）。 |
| 测试 | 新增 `tests/integration/g4r_recovery/`：**19 passed**（R2-01..R2-09 全覆盖，含真实本地 Broker/Fake 子进程用例）。 |
| 回归 | 相关 bridge/g4 回归 427 项：**426 passed / 1 skipped / 1 failed**；唯一失败 `g3d/test_d3_contract.py::test_runner_does_not_modify_product_src` 属**冻结基线已存在的 known 失败**（`git diff --quiet 4bd4803 -- src` 在未改动的 main 工作树同样 exit 1），不是本 PR 回归（§7）。 |
| L2 | **UNVERIFIED / BLOCKED_NEEDS_ENVIRONMENT**：本轮未重建含新 `src` 的 Stage、未起 podman 容器、无 Stage/Runtime SHA；禁止把 L1-HOST 记为 L2 PASS。 |

---

## 1. P2-05：真实时间线与观察层归属（先证明，后实现）

### 1.1 复现的真实时间线（证据根 `probes.json`、`raw/timeout-layer/`）

用例：admission `deadline_ms=800`，`G3B_TEST_MODE=1`、`G3B_TEST_DELAY_HOOK=before_reserve`、
`G3B_TEST_DELAY_MS=2500`；真实本地 Broker/Fake 子进程；客户端逐帧消费流。

在客户端收到 `DEADLINE_EXCEEDED` 的瞬间：

```json
error_code = "DEADLINE_EXCEEDED"
request_lifecycle = [received, controller_entered, deadline_before_controller]
deadline_before_controller = {
  "stage": "before_reserve", "controller_entered": true,
  "dispatch_seq": 1, "reserved": false, "code": "DEADLINE_EXCEEDED",
  "reason": "transport_observed_deadline"
}
dispatch_window_at_deadline_instant = []          # F5-R4 的实际缺口
broker_requests = 0, fake_received = 0, attempts = [], pending_intents = []
```

结论（不是猜测）：该 timeout **由 request/transport 层观察到并结束流**，而 dispatch 层
worker 仍阻塞在 `before_reserve`、其 `finally` 记录尚未落盘；所以旧行为下
`dispatch-window.jsonl` 缺失是**可解释的证据丢失**，不是“没有请求”。
请求层 journal 同步写（`os.write+fsync`）因此能在 worker 被 launcher 终止/尚未落盘时
保留真实层级。in-process 测试随后关闭流触发真实 `finally` join，worker 最终写出的
dispatch 行仍是 `reserved=false, dispatched=false, settled=false`，从不声称发送。

### 1.2 两层 journal（概念分离）

| 文件 | 层 | 写入者 | 语义 |
|---|---|---|---|
| `request-lifecycle.jsonl`（新增） | transport/请求层 | `handle_envelope`（主线程）+ worker 的进入/</br>pre-Reserve 失败通知 | `received` / `protocol_rejected` / `deadline_before_controller` / `cancel_before_controller` / `controller_entered` / `failed_before_reserve`；`reserved` 恒 `false` |
| `dispatch-window.jsonl`（既有） | Controller dispatch 层 | 真实进入 `_handle_payload_serial` 的请求 | `reserved/dispatched/settled` 只属于真实 dispatch；protocol-only rejection 兼容行为 `dispatch_seq:null + request_level_only:true` |
| `recovery-diagnostics.jsonl`（新增） | recovery 观察层 | `reconcile_on_startup` | 每次 reconcile 决策一行：`primary_cause`、`primary_cause_preserved`、`reconciliation_observation`、`broker_status`、`action` |

事件字段白名单（请求层）：`schema=m0.g4r.request-lifecycle.v1`、`version`、`utc`、
`event`、`stage`、`code`、`reason`（异常类名/稳定原因）、`request_seq`、
`transport_id_sha256`（原始 transport id 不写）、`origin_uid`/`origin_kind`
（内核报告 peer，数字）、`purpose`（`conversation`/`null`/`<missing>` 等有界枚举视图）、
`instance_id`、`reserved=false`、`controller_entered`、`dispatch_seq`（仅真实分配时出现）。
**不含** prompt、message、tool 参数、session 文本、Key、凭据。`request_seq` 与
`dispatch_seq` 是两个独立计数：未进入 Controller 的事件 `dispatch_seq` 必为 `null`。

R2-01 附带用例证明：pre-start cancel 的 lifecycle 为
`[received, cancel_before_controller]`，`dispatch-window.jsonl` 为 **0 行**，
`dispatch_seq=null` —— 未进入 Controller 的请求不伪造任何 dispatch。

---

## 2. P2-06：first_cause 与 reconciliation_observation 分离

### 2.1 设计决策（先核对 Schema/依赖）

- 不改 Attempt SQLite schema（`g3b_attempts.reason` 仍是唯一 first-cause 字段）；
  新增 **append-only JSONL** `recovery-diagnostics.jsonl`（与 Attempt DB 同目录、
  `0600`、`O_NOFOLLOW`、每行 fsync），避免迁移/双写风险。
- 保留 primary cause 的**封闭枚举**：`RUN_AUTHORIZATION_REVOKED` 精确值 +
  `REVOKED_PRE_SEND:` 前缀；其它任何非空 reason **不**冻结（防止隐藏新的严重状态，
  对照 G4-R 计划 §5.2 第 3 条“不可仅对任何非空 reason 一律不更新”）。
- 仅当 Broker 查询成功且状态为 **`PENDING`** 时才保留 primary cause；Broker
  `OK/FAILED` 仍优先归档为 `SETTLED/WORST_CASE_HELD`，本地证据缺陷不阻止终态同步。
- 每次 reconcile 决策（含已终态 skip、status unavailable/unknown、settle/fail 失败分支）
  都追加一条 diagnostics；该行是观察，不是费用/结算权威。

### 2.2 决策表（实测行为）

| 旧 Attempt | 旧 reason | Broker | 结果 `state` | 结果 `reason` | diagnostic |
|---|---|---|---|---|---|
| `RESPONSE_OBSERVED` | `REVOKED_PRE_SEND:RUN_AUTHORIZATION_REVOKED` | `PENDING` | `SETTLEMENT_UNCERTAIN` | **保留** `REVOKED_PRE_SEND:RUN_AUTHORIZATION_REVOKED` | `primary_cause_preserved=true`、obs=`RECEIPT_DOCUMENT_SCHEMA_INVALID`、action=`MARK_SETTLEMENT_UNCERTAIN` |
| `RESPONSE_OBSERVED` | 其它非空（如未知新原因） | `PENDING` | `SETTLEMENT_UNCERTAIN` | 覆盖为具体 observation（如 `RECEIPT_DOCUMENT_SCHEMA_INVALID`） | `primary_cause_preserved=false`、`prior_reason_class=OTHER` |
| `ATTEMPT_STARTED` | 无 | 未查询 | `SETTLEMENT_UNCERTAIN` | `NO_RECEIPT_AFTER_CRASH` | obs=`NO_RECEIPT_AFTER_CRASH`、`primary_cause=null` |
| 任意（receipt 无效） | 任意 | `OK` | `SETTLED` | 保留旧 reason（settlement_json 记 `local_evidence_reason`） | action=`MARK_SETTLED`、Broker 权威 |
| 任意（receipt 无效） | 任意 | `FAILED` | `WORST_CASE_HELD` | `BROKER_ALREADY_FAILED:<obs>` | action=`MARK_WORST_CASE` |
| 任意 | 任意 | 查询失败/未知 | `SETTLEMENT_UNCERTAIN` | 现有稳定原因（`BROKER_STATUS_UNAVAILABLE`/`UNKNOWN`） | `broker_authoritative=false` |

实测证据（`recovery-evidence.json` + `raw/recovery/recovery-diagnostics.jsonl`）：
revoked + corrupt receipt + Broker `PENDING` → `reason` 保留 revoke、
settle/fail 调用次数 0、`Fake=0`、diagnostic 同时记录 `RECEIPT_DOCUMENT_SCHEMA_INVALID`。

### 2.3 不变量（与计划 §1.2 / §5.2 对齐）

- Broker committed `OK/FAILED` 仍为唯一终态权威；本地原因保持不阻止终态同步。
- 同一 reservation 的 settle/fail 仍然至多一次（既有路径未改；实测第二次 reconcile 不再
  settle/fail，`diagnostics` 不再追加）。
- `PENDING/UNCERTAIN` 保持 held>0：不因新 journal 自动 release/free，不盲重发（R2-02）。
- 新 journal 是 **additive** 证据；写失败只计 gap（见 §3）。

---

## 3. 观测失败语义（P2-05 观测写失败 / R2-04）

- `RequestLifecycleAudit` / `RecoveryDiagnostics` 的每次写失败只增加
  `write_errors`、记录 `last_error`（异常类型名，不写内容）；`TrustedController
  .observability_status()` 返回：
  `{"observability_gap": true, "safety_admission_changed": false, ...}`。
- 实测：请求级 journal 父目录不存在 → 成功请求仍 1 Reserve/1 Claim/1 Fake/1 SETTLED；
  dispatch journal 路径为目录 → 决策不变、请求层 journal 仍独立记录；`/dev/full`
  真实 ENOSPC → `write_errors>=1, written=0, observability_gap=true`。
- 安全关键的 Gate 授权 journal 不在本 PR 改动范围，仍 fail-closed。
- **未覆盖**：外部 SIGKILL 的全部纳秒级窗口（F5-R6 / G4-R R5 范围）；本轮只做
  in-process 异常路径 + ENOSPC 实写失败，矩阵中 SIGKILL 子项标 `UNVERIFIED`。

---

## 4. 变更文件表

| 文件 | 变更 |
|---|---|
| `src/autoteacher_m0/bridge/controller.py` | additive：optional `request_lifecycle` / `recovery_diagnostics` 路径；请求层 6 类事件写入点；dispatch 层 rejection 行去 `dispatch_seq`；`_Cancelled→CANCELLED` 映射；`reconcile_on_startup` first_cause 保留 + diagnostics 全分支；`main()` 默认 journal 路径；`observability_status()` |
| `src/autoteacher_m0/bridge/request_lifecycle.py`（新增） | 请求级 JSONL writer、字段白名单、`request_seq`、`transport_id_sha256`、gap 计数 |
| `src/autoteacher_m0/bridge/recovery_diagnostics.py`（新增） | recovery observation JSONL、封闭 primary-cause 枚举、action 常量、gap 计数 |
| `tests/integration/g4r_recovery/`（新增 8 文件） | R2-01..R2-09 host 合同测试（真实本地 Broker/Fake + 受控 stub Broker）、无外部网络 fixture |
| `scripts/g4r/run_r2_evidence.py`（新增） | R2 证据采集：pytest + 真实 timeout 层级 probe + recovery probe + env/SHA/UTC/exit |
| `docs/M0_G4R_R2_RECOVERY_REPORT.md`（本文件） | 报告 |

改动范围仅 `src/autoteacher_m0/bridge/`、`tests/`、`scripts/g4r/`、`docs/`；证据在
gitignored `artifacts/g4r/r2/`。

---

## 5. 逐 case 证据（L1-HOST 实测；L2 见 §8）

所有命令均在 `/root/Autonomous Teacher/worktrees/g4r-recovery`、`PYTHONPATH=src`、
`"/root/Autonomous Teacher/.venv/bin/python" -m pytest ... -q -p no:cacheprovider` 下执行；
证据运行 `host_head=7bd7fa2e…`、`host_parent=4d59f22d…`、exit=0、UTC
`2026-11-20T16:32:45Z–16:33:0xZ`（见 `env.json`/`pytest.txt`）。

| Case | 方法（nodeid 见下） | 关键断言 | 状态 |
|---|---|---|---|
| R2-01 | `tests/integration/g4r_recovery/test_r2_01_pre_controller_deadline.py` | 800ms/2500ms 真实层级：`[received, controller_entered, deadline_before_controller]`，`stage=before_reserve`、`controller_entered=true`；deadline 瞬间 dispatch 行 0；0 Broker/0 Fake/0 Attempt/0 intent；pre-start cancel → 0 dispatch 行、`dispatch_seq=null`；最终 dispatch 行 `reserved/dispatched/settled=false` | **PASS (L1-HOST)** |
| R2-02 | `test_r2_02_post_reserve_hold.py` | post-Reserve cancel/timeout：Broker `requests=1, pending=1, reserved>0`，intent `HELD_UNCERTAIN`，0 Fake，dispatch 行 `reserved=true, dispatched=false, settled=false`；无 FREE/release | **PASS (L1-HOST)** |
| R2-03 | `test_r2_03_request_rejection.py` | schema 错 / 辅助 purpose / 外来 raw-UDS peer：Protocol code 一致；`protocol_rejected`（未进入 Controller）或 `failed_before_reserve`（进入但 pre-Reserve）；0 Reserve/Claim/Fake；未进入者 dispatch 行 `dispatch_seq=null/request_level_only=true` | **PASS (L1-HOST)** |
| R2-04 | `test_r2_04_observability_gap.py` | 请求层/dispatch 层写失败 + `/dev/full`：`observability_gap=true`、`safety_admission_changed=false`；决策/Fake/SETTLED 不变；SIGKILL 子项未测 | **PASS (L1-HOST)**；SIGKILL 子项 `UNVERIFIED` |
| R2-05 | `test_r2_recovery_semantics.py::test_r2_05_*` | revoked + corrupt receipt + PENDING：`reason` 保留 `REVOKED_PRE_SEND:RUN_AUTHORIZATION_REVOKED`；diagnostic 记 `RECEIPT_DOCUMENT_SCHEMA_INVALID`；settle/fail=0；Fake=0；非已证 reason 不被冻结 | **PASS (L1-HOST)** |
| R2-06 | `...::test_r2_06_*` | 无既有原因 crash → `NO_RECEIPT_AFTER_CRASH`（已知枚举），不填误导原因；diagnostic `primary_cause=null` | **PASS (L1-HOST)** |
| R2-07 | `...::test_r2_07_*` | corrupt receipt（非 JSON）+ revoked 并存：保留 revoke、diagnostic 记 `RECEIPT_DOCUMENT_INVALID`、settle/fail=0、Broker 仍 PENDING | **PASS (L1-HOST)** |
| R2-08 | `...::test_r2_08_*` | Broker `OK`/`FAILED` + 本地坏证据：`SETTLED`/`WORST_CASE_HELD` 恰一次、无第二次 settle/fail、无状态逆转；二次 reconcile 幂等 | **PASS (L1-HOST)** |
| R2-09 | `...::test_r2_09_*` | 只读 URI 读原始 DB 行 + JSONL 独立对账：held attempt 数 == Broker PENDING hold 数；settle/fail=0；diagnostic 字段 bounded | **PASS (L1-HOST)** |

复现命令：

```bash
cd "/root/Autonomous Teacher/worktrees/g4r-recovery"
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/integration/g4r_recovery -q -p no:cacheprovider
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" scripts/g4r/run_r2_evidence.py
```

**证据根**：`artifacts/g4r/r2/20261120T163245Z-7bd7fa2/`（gitignored）
含 `env.json`（SHA/UTC/exit/0 key/0 HTTP/L2 UNVERIFIED）、`pytest.txt`（19 passed）、
`junit.xml`、`probes.json`、`raw/timeout-layer/{request-lifecycle,dispatch-window}.jsonl`、
`raw/timeout-layer/timeout-layer-{at-deadline,after-teardown}.json`、
`raw/recovery/recovery-diagnostics.jsonl`、`raw/recovery/recovery-evidence.json`、
`regression.txt`。

---

## 6. L1-HOST 与 L2 分级

- 本轮实测证据等级为 **L1-HOST**：真实 Controller 代码路径、真实本地 Broker/Fake
  子进程（synthetic fixture）、真实文件系统与 JSONL/SQLite 读取；**无容器、无真实 DSH**。
- 矩阵 `R2-01..R2-09` 的目标等级是 `L2-REAL-DSH`。本轮**未**执行 L2（§8），
  因此不得把上表 `PASS (L1-HOST)` 写成 L2 PASS；矩阵状态建议
  `PARTIAL / L2 UNVERIFIED`（由 Lead/Integration 决定，CSV 不由本 Agent 修改）。

## 7. 回归

| 范围 | 结果 | 说明 |
|---|---|---|
| `tests/integration/g4r_recovery`（新） | **19 passed** | R2-01..R2-09 |
| `g3_bridge/g3c/g3d/g4_f2/g4_f3/g4_f5/g4_c` | **426 passed / 1 skipped / 1 failed**（`regression.txt`） | 唯一失败 `g3d/test_d3_contract.py::test_runner_does_not_modify_product_src`：该测试断言 `git diff --quiet 4bd4803 -- src`，在**未改动的 main 工作树**同样 exit 1（已实测），属 G4-F 已知 frozen-src 环境项，不是本 PR 回归 |
| `ruff check`（全部变更文件） | **0 finding** | `ruff 0.17.5` scoped |

未跑：Host full、固定 OCI filtered、Node TAP（属 R4/Integration 范围，本轮时间盒内不占用）。

## 8. L2（真实 DSH/容器）— 如实标 UNVERIFIED

- 未重建包含本 PR `src` 的 Stage，未启动 podman 容器，未获取 Stage/Runtime/rootfs/deps SHA；
  因此 `R2-01..R2-09` 的 `L2-REAL-DSH` **NOT_RUN → UNVERIFIED / BLOCKED_NEEDS_ENVIRONMENT**。
- 理由：本轮时间盒优先完成“观察层分离 + recovery 语义 + L1 合同测试”；重建 Stage 需
  Integration/R4 统一冻结口径，不能复用旧 Stage 字节冒充新代码（G4-R §9.1）。
- 复用既有 harness 的建议入口（未执行）：`tests/integration/g4_f5/run_f5_evidence.py`、
  `scripts/g4/launch_c.py`、stage 构建脚本；待 Lead 排期后用含 `4d59f22`/`7bd7fa2`
  的自建 Stage 重跑 `timeout-pre-send`、`revocation-post-reserve`、
  `timeout-post-send` 三条关键 case，并把 Stage/Runtime SHA 写入矩阵。

## 9. 与 F5 历史证据的关系

- 不覆盖、不改写旧 `docs/M0_G4F_F5_REPORT.md`（F5-R4/F5-R5 原始记载仍有效）与
  `docs/REVIEW_G4F_INDEPENDENT.md` §7/§11 的 P2-05/P2-06 判定。
- 本报告用新 case ID `R2-01..R2-09` 记录改善：
  - F5-R4 的“`timeout-pre-send` 无 dispatch-window 记录”→ 现在有**请求层**真实层级记录
    （同步落盘 + `stage=before_reserve` + `controller_entered=true`），dispatch 层仍诚实
    缺失/迟到，不伪造；
  - F5-R5 的“recovery 覆盖 revocation reason”→ 现在 primary cause 在 Broker PENDING
    时保留，observation 进独立 append-only 文件；账本状态/held 语义未变。
- F5-R6（外部 SIGKILL 纳秒窗口）与 F4/F5 其它残余不因本 PR 关闭。

## 10. Prior art（只读参考，非 base）

`work/m0-g4h0` @ `15c5a08` 有简化版“observation-only + reason 合并”实现
（同一 `dispatch-window.jsonl` 追加 `observation_only` 行、`|RECOVERY_EVIDENCE:` 合并原因）。
G4-R 要求更严格（独立请求层文件、未进入 Controller 不消耗 `dispatch_seq`、first_cause
独立观察、封闭枚举 + Broker PENDING 条件），因此本分支**独立实现**，未 merge/cherry-pick
该分支，也未以其为 base。

## 11. 残余风险与未验证项

| ID | 残余 | 处置 |
|---|---|---|
| R2-L2-01 | `R2-01..R2-09` 的 L2-REAL-DSH 未执行 | UNVERIFIED，待 Stage 重建后补 |
| R2-L2-02 | 真实 DSH 会话在 deadline 时被 launcher 终止的进程行为未在 L2 重放 | L1 已证明“deadline 记录先于 worker finally 落盘”的机制；L2 待补 |
| R2-04-SIGKILL | 外部 SIGKILL 的时序窗口未穷举（F5-R6 同类） | UNVERIFIED；只测 in-process 异常 + ENOSPC |
| R2-P2-05-A | `_Cancelled` 的 dispatch-row `error_code` 由 `INTERNAL` 修正为 `CANCELLED`（本次 additive 修正） | 仅改善分类；不影响准入 |
| R2-P2-06-A | primary cause 保留范围严格限定两个已证枚举 + Broker PENDING；更广原因不冻结 | 有意保守，防止隐藏新严重状态；Reviewer 可独立攻击 |
| R2-P2-06-B | diagnostics 是 JSONL，崩在写失败时仅计 gap，不重试不阻塞恢复 | 与计划“写失败默认不改变纯观测判定”一致；关键安全 Gate journal 未变 |

## 12. 结论

本 PR 在 L1-HOST 范围内完成 G4-R §5 的 P2-05/P2-06 修复：请求级与 dispatch 级观察
概念分离、未进入 Controller 不伪造 dispatch、timeout 层级以真实时间线证明；recovery
first_cause 与 reconciliation observation 分离且 Broker 权威/at-most-once/held 语义不变。
L2-REAL-DSH 证据与 SIGKILL 窗口仍未验证，**不得**据此宣称 G4-R 全链 PASS，也不改变
G4-H/G5/LiveGate 状态。
