# M0 G2-L1-FIX Report — egress claim bypass / approved route-model binding（离线/无 Key）

- 任务：`task-80`（G2-L1-FIX，A0–A3 + Lead 审计补齐 G1/G2/G3 + A2 请求绑定）
- 日期：2026-11-15 UTC；基线：G2 最终代码 `32bea5b`；工作树 HEAD 基线 `688ed01`（docs commit）
- 范围：**仅 G2-L1-FIX**；不进入 G3/G4/Live，不签发 GO，不声称远端 exactly-once。
- 安全边界：固定无 Key/禁网/只读/non-root OCI；0 真实 Key/模型/HTTP/socket 外呼；未读 `/root/.config/autoteacher`。
- 约定：本地 claim ≠ 远端/provider exactly-once；FakeProvider 为 synthetic；真实 wire/usage/invoice/正式 tool 注册表属 G3_DEPENDENCY。

## 1. 范围与基线

| 项 | 值 |
|---|---|
| G2 代码基线 | `32bea5bcf8d35d778a54c04bb0ae08fb1f849c` |
| 工作树基线 | `688ed018ea9a4b878f989571a26ab78ff55abb1d`（docs/closeout） |
| 实现 commit | **`2786e25a9e5bd590255026d76fc362abb16d0e7b`**（父 `688ed01`） |
| docs commit | 本报告所属 docs commit（见 git log；生成时不可自引用自身 SHA） |
| 未改 | `security/gates.py`、`runtime/dsh_adapter.py`、`scripts/run_live.sh`、历史冻结证据 |
| 不改协议外的 Live 面 | LiveGate/E1–E5/真实 Key/egress/usage/账单仍 **BLOCKED / DECISION PENDING** |

## 2. A0–A3 摘要

- **A0 RED**：在旧代码 stage 上新增 fail-first 测试，真实 **10 failed / 2 xfailed**（L1-a..e/bool/BIND 设计占位），证明缺口真实；环境 smoke **17 passed**。
- **A1**：拆分 `PolicyEvaluation`/`evaluate_descriptor`/诊断 `authorize/require` 与 `DispatchPermission`/`TrustedEgressTransport`；无 claimer fail-closed；严格 policy/request；OBS-1 attempt detail；g2/sandbox 测试迁移。
- **A1 审计补齐**：G1 进程内 permission 登记 + `consume_permission`（伪造/篡改/跨 boundary/重放均 0 provider）；G2 strict loader 重复/空白拒绝；G3 path traversal/backslash/`%2e`/控制字符拒绝。
- **A2**：Lead 批准 **Option A**；新增 `PreparedProviderRequest`/canonical digest/`claim_dispatch_for_request`/`BoundBrokerClaimer`；broker claim 可选成对 `expected_route_id`/`expected_model`，ledger 写 claim 前与 reservation row 比较 → `ROUTE_MISMATCH`；旧 v1 兼容、旧客户端省略字段残余明确。
- **A3**：严格 policy/请求类型、快照归因、测试清理、验证脚本迁移。

## 3. 真实测试矩阵

### 3.1 新增/迁移用例（`tests/integration/g2_closure/test_g2l1_fix.py`、`test_g2l1_red.py`）

| 组 | 用例 | 状态 |
|---|---|---|
| FIX-01..08 | descriptor policy-only；无 claimer fail-closed；claim 异常/坏回复/denied；descriptor deny 不调用 claimer；伪 permission 拒绝；真实 permission 一次 dispatch；permission 绑定/重放；真实 SQLite+stdio claim+一次 synthetic dispatch | **PASS** |
| BIND-01 | 真实 SQLite + stdio Broker：Reservation=A/实际 B（均 allowlist）→ ledger `ROUTE_MISMATCH`、无 claim、provider=0 | **PASS** |
| BIND-02 | prepared 消息/digest 变更 → deny、claimer/provider=0 | **PASS** |
| BIND-03 | maxTokens 256→512 → deny、claimer=0 | **PASS** |
| BIND-04 | method/path/host 绕过 → deny、claimer=0 | **PASS** |
| BIND-05 | 未批准 tools schema → `TOOL_SCHEMA_NOT_APPROVED`、claimer=0；正式注册表 G3_DEPENDENCY | **PASS（egress 侧）** |
| BIND-06 | 重复/重放 bound claim 至多一次 | **PASS** |
| BIND-07 | 未修改成功一次、ledger `claims.total=1` | **PASS** |
| BIND-08 | 仅 reserve.dispatch_allowed、无 claim → provider=0、claims=0 | **PASS** |
| STRICT-01..04 | bool/int 严格、未知字段/范围、重复 method/port/空白、path traversal 负例 | **PASS** |
| TRACE-01 | 同一 logical stream 多 reservation 的 `attempts_detail` 关联 | **PASS** |
| PROC-01 | stdio Broker 子进程 close 后无泄漏 | **PASS** |
| v1 兼容 | 旧 claim（无 expected 字段）仍成功；新 egress 对无 bound claimer → `CLAIM_BINDING_UNSUPPORTED` deny，provider=0 | **PASS（残余注明）** |

### 3.2 真实计数（固定无 Key OCI；宿主未跑 pytest）

| 选择集 | 结果 | 日志 |
|---|---|---|
| focused：`test_g2l1_red.py` + `test_g2l1_fix.py` + sandbox `test_egress_boundary.py` | **98 passed**，exit 0 | `artifacts/g2l1/logs/a2-final-focus.stdout.log` |
| 回归：`tests/integration/g2_closure tests/integration/sandbox tests/unit/security` | **256 passed, 1 skipped**，exit 0 | `a2-final-regression.stdout.log` |
| 全量：`tests/`（绑定 impl commit `2786e25` 的 git-archive stage） | **601 passed, 1 skipped**，exit 0 | `artifacts/g2l1/logs/impl-full.stdout.log` |
| `scripts/verify_egress_policy.py` | **status=PASS**，exit 0 | `a2-final-script.stdout.log` / `impl-script.stdout.log` |
| Ruff repo-wide | **All checks passed!** | `a2-final-ruff.stdout.log` / `impl-ruff.stdout.log` |

> 计数为实际 pytest 输出；未预填、未用 skip/xfail 掩盖。Focused/回归中的 1 skip 为既有环境 skip；无 xfail（A0 设计占位已移除，BIND-01 真实覆盖）。

## 4. v1 兼容结论

- 旧 `snapshot/reserve/settle/fail` 行为不变；旧 claim 不带 `expected_route_id`/`expected_model` 仍成功（显式测试），broker/ledger claim 表结构不变。
- 新受信 egress 必须使用 `BoundBrokerClaimer`；若 claimer 无 `claim_bound` → 显式 `CLAIM_BINDING_UNSUPPORTED` deny，不静默发送。
- **残余缺口（明确）**：旧客户端省略 expected 字段时 ledger 无法强制 route/model 绑定；该残余存在，不得写“所有 claim 均已强制绑定”。新 egress 的 BIND-01 由 ledger 权威 `ROUTE_MISMATCH` 覆盖。

## 5. 残余 / G3_DEPENDENCY

1. 真实 provider wire 字节/digest 与 `PreparedProviderRequest` 的远端一致性未验证（G3）。
2. 正式 tool schema 注册/审批表未实现；A 仅做输入负例（G3）。
3. 远端/provider exactly-once、真实 usage/invoice/账单未验证（G3）。
4. 旧 v1 客户端省略 expected 字段的 binding 残余缺口（G3/v1 迁移）。
5. TrustedEgressProvenance 仍是同进程 capability（V-G1-3），不是密码学来源认证；真实 egress/Key Broker 未部署。
6. 本地 claim 不是远端 exactly-once；claim granted 未发送保持保守 pending，无自动退款/重试。

## 6. 安全非主张 / STOP

- **不主张**：真实 Live PASS、真实 wire/HTTP/socket、真实模型/Key/usage/账单、远端 exactly-once、G3/G4 已完成。
- 0 真实 Key/网络/模型；未读凭据；容器 absence=0；不改 `gates.py`/`dsh_adapter.py`/`run_live.sh`；不重写历史证据。
- **STOP**：G2-L1-FIX 完成；G3 未启动。等待 Lead 审阅 implementation/docs commit 与 Review Packet 后，才派独立 reviewer。
