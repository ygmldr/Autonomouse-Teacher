# G2 独立审计 — Canonical CallIdentity、持久 Dispatch Claim、真实 SQLite/stdio 闭环

- 任务：`task-67`；日期：2026-11-15 UTC；审计者：`verify2`（非实现者）
- 对象：**G2-BROKER** `ada8e28d7afb6a5c7cbca0a16ae955ec3b22578b`（父 `70cb574`，8 files）；**G2-EGRESS** `32bea5bcf8d35d778a54c04cebb0ae08fb1f849c`（父 `ada8e28`，4 files）；HEAD=`32bea5b`，worktree clean
- 报告锚：`docs/M0_G2_BROKER_REPORT.md` `d262514b…`、`docs/M0_G2_INTEGRATION_REPORT.md` `824aef3d…`、`docs/ADR-002-unified-call-identity.md` `22d277d1…`
- 证据锚：`artifacts/m0-g2-broker/` manifest `c237d950…`，evidence **26/26**；`artifacts/m0-g2-integration/` manifest `1b59180e…`，evidence **40/40**
- **结论：`PASS_FOR_DECLARED_G2_SCOPE`**（仅限离线/无 Key G2；真实 provider wire/usage/invoice、真实 Key/egress/LiveGate 仍 BLOCKED/DECISION PENDING，不签发 GO）。**1 项条件性遗留 G2-L1（legacy `EgressBoundary.authorize()` 仍可被直接调用，非当前生产接线，但需在 G3/Live 前收口）** 和 1 项非阻断证据身份问题 V-G2-1。

## 1. 方法与隔离

- 独立 stage：`git archive 32bea5b`（**186 files**，tar sha256 `6c2175b3996ea7e7dfbd7b703cebbc3cab895b3a91247dceca1eee527742714f`）；G2 实现/测试文件 hash 与 owner manifest 一致。
- 固定 digest 无 Key 禁网 OCI：rootfs `25491e45…`、deps `e07729d7…`、`--network none`、read-only rootfs、uid 65534、cap-drop ALL、no-new-privileges、pids/mem/cpu 限制、`/tmp`+`/work` noexec tmpfs；宿主未跑项目代码。
- 0 真实 Key/模型/HTTP/socket 外呼；broker 子进程通过 stdio pipe + 真实 SQLite 文件；FakeProvider 为 in-process synthetic；容器 absence=0；rootfs/deps canonical；未读凭据。

## 2. Git/范围与历史证据

| 检查 | 结果 |
|---|---|
| G2-BROKER 8 files | ADR/report、`call_identity.py`（新）、`broker.py`/`ledger.py`/`observation.py`（改）、`test_g2_dispatch_claim.py`、`test_call_identity.py` |
| G2-EGRESS 4 files | integration report、`security/egress.py`、`test_g2_closure.py`（新）、`test_egress_boundary.py`（改） |
| 混入/越权 | 无 guard/adapter/gates/run_live/accounting 非授权修改；`git diff --check` 0；两 commit 范围与 owner 声明一致 |
| Live 面 | `security/gates.py`/`runtime/dsh_adapter.py`/`scripts/run_live.sh` 相对 `70cb574` **0 改动**（同 hash） |
| 历史证据 | phase5 `391767d3…`、PR1 `df14f3c1…`、G1 security `4ef23f69…`、G1 accounting `cb780a39…` 字节未改 |
| owner evidence | broker **26/26 OK**、integration **40/40 OK**；报告 hash 与锚一致 |

## 3. 独立重跑（固定 digest 无 Key OCI；新 argv/UTC/exit 见 `artifacts/reviewer-g2/raw/commands.jsonl`）

| 用例 | 结果 |
|---|---|
| G2 targeted（g2_closure + test_g2_dispatch_claim + test_call_identity + 原 egress boundary） | **56 passed**，exit0（我额外纳入原 egress legacy 测试；owner targeted 42 为其子集） |
| full integration（security/sandbox/accounting/budget_bridge/g2_closure） | **367 passed, 1 skipped**，exit0（与 owner full 367/1 一致） |
| 旧实现 fail-first（owner `stage-old`：70cb574 代码 + 新测试） | **1 collection error**（`call_identity` 缺失，exit2；owner 另有 9 failed integration，日志一致） |
| Ruff scoped `src tests` / repo-wide | **All checks passed!** / **All checks passed!** |
| INT 矩阵 | 独立 full 中 `tests/integration/g2_closure` 覆盖 INT-01..18；owner manifest `int_matrix` 18/18 PASS，测试用例名一致（INT-01/02/03/04/05/06/07/08/09/10/11/12/13/14/15/16/17/18） |

## 4. 语义核验（源码 + 测试）

### Canonical CallIdentity（ADR-002）
- `accounting/call_identity.py:18-20` 定义 `call-[0-9a-f]{48}`/64-hex digest；`:58-85` `CallIdentity` 严格字段 + canonical json + stable hash；`observation.py` re-export 兼容旧 import（owner 报告）。
- Egress 强制 `call_id`/`request_digest`（`security/egress.py:156-160`）；`eg-...` 只出现在 `_legacy_egress_event_id` 日志字段（`:126-132,:190`），不进入 decision.call_id/claim/settlement；broker/ledger 只接受 canonical `call-`（owner tests/`test_int07/08`）。
- `CallIdentity`/`eg-` 不混用：测试 `test_call_identity.py` 断言 stability/bounded/injective；`test_legacy_egress_ids_are_rejected_as_settlement_ids` 通过。

### 持久唯一 claim（单事务）
- `ledger.py:189-272` additive `budget_dispatch_claims` 表；`claim_dispatch()` 在同一事务内校验 scope/reservation PENDING/预算 bound/route/link/digest/唯一性，`INSERT` 后处理 race（`CLAIM_RACE_LOST`/`ALREADY_CLAIMED`）；`:275-295` `claim_for_call`/`mark_claim_completed`/snapshot claims。
- `broker.py:171-192` additive v1 `claim` op（不在 journal 计费消息，独立 durable claim 表）；`:219-226` reserve 绑定、`:265` settle 完成 claim。
- 测试：INT-01 claim→settle→COMPLETED；INT-04 duplicate `ALREADY_CLAIMED` 0 dispatch；INT-05 两个真实 broker 进程并发恰一个 `dispatch_allowed=true`；INT-06 SIGKILL 后重启 replay 不再许可；INT-07 digest conflict；INT-12 scope blocked/broker down 0 grant；INT-17 同 reservation 第二次 call 拒绝；INT-18 重启 balance/claims durable。全部独立 full 通过。

### Egress claim gate / FakeProvider
- `egress.py:215-245` `claim_dispatch` 先 `_evaluate`，再调用真实 `BrokerClaimer`；claim 失败追加 `CLAIM_REJECTED:<code>` 且不 dispatch；`StdioBrokerClaimer` 在 `test_g2_closure.py:65-100` 真 subprocess stdio。
- FakeProvider `test_g2_closure.py:133-166` scripted synthetic，`network_attempts=0`；INT-01/15/16/18 验证 settled once、伪造 AUTHORITATIVE 不结算、tampered output 不静默接受、重启不减少 balance。
- 真实 SQLite：`make_config`/`BudgetLedger` 使用 `tmp_path/ledger.sqlite3`；claim cross-check via broker snapshot (`claims.total/pending/completed`) + ledger settle state；`real_network_attempts=0`、`fake_provider_network_attempts=0`。

### Broker v1 兼容
- 旧 `snapshot/reserve/settle/fail` 字段/语义不变；`claim`/`snapshot.claims` 为 additive；`reserve.call_id` 可选，旧客户端不发时保持原行为；`eg-` 仅 legacy log；旧测试/回归在 full 367 中通过。

## 5. 发现

### G2-L1（条件性遗留；不阻断当前声明 G2，但需 G3/Live 前收口）
`EgressBoundary.authorize()` 仍是公开的无 claim descriptor 路径：
- `security/egress.py:210-213` `authorize()` 只调用 `_evaluate`/`_record`，不调用 broker claim；
- `:215-225` `claim_dispatch()` 在 `claimer is None` 时走 descriptor-only legacy 路径并返回 allowed；
- `:284-288` `require()` 仍调用 `authorize()`；
- `:317-324` `MockEgressTransport.dispatch()` 若 boundary 未配置 claimer，回退到 `authorize()`；
- `security/__init__.py` 公开导出 `EgressBoundary`/`MockEgressTransport`。
**风险判断**：当前仓库 `src/` 无生产调用 `authorize()/require()`（grep 仅 `scripts/verify_egress_policy.py` 与 tests；G2 integration 使用真实 `StdioBrokerClaimer`）；LiveGate/adapter/run_live 仍 BLOCKED，故**不是当前生产绕过**。但公开 API 默认无 claimer、MockEgressTransport 回退 legacy 会让未来接线在忘记注入 claimer 时静默绕过“一次许可”；建议 G3 前将 claimer 设为强制/`authorize()` 私有化或移除 legacy fallback，并审计所有调用点。**标记 CONDITIONAL，不阻断 G2 declared scope；不得把“所有 egress 已强制 claim”写成结论。**

### V-G2-1（证据身份；非阻断）
broker manifest `implementation_sha=null`；integration manifest `baseline_head=ada8e28`（G2-BROKER freeze，不是最终 HEAD 32bea5b）；报告也以“基线/未提交”描述。实际 G2 实现提交为 `ada8e28`（broker）+ `32bea5b`（egress）；本审计按两 commit 独立绑定，文件 hash 与 owner 一致。建议 post-freeze errata 明确记录两个最终实现 commit（不重写旧字节），G3 review packet 绑 `32bea5b`。

## 6. 残余 UNVERIFIED / BLOCKED（不夸大）

1. 真实 provider wire/usage/invoice、真实 Key/egress/Key Broker、LiveGate/E1–E5 仍 **BLOCKED**；本 PASS 仅离线 G2。
2. local claim 不是远端 exactly-once；claim granted 但未发送保持 CLAIMED/pending（保守，无退款/重试）；真实 reconciliation 未实现。
3. FakeProvider 为 scripted synthetic；network attempts 0；不是真实模型/HTTP/账单证据。
4. TrustedEgressProvenance 仍是同进程 capability（V-G1-3），不是密码学来源认证；G2 未部署真实可信 egress 边界。
5. G2-L1 legacy `authorize()` 路径未强制 claim；G3/Live 前必须收口/移除绕过面。
6. broker v1 兼容仅由离线测试证明；真实旧客户端/远程 broker 未验证。

## 7. 证据索引

- 独立 stage：`artifacts/reviewer-g2/stage.tar`（`6c2175b3…`，186 files）+ `stage/`；运行日志/`raw/commands.jsonl`。
- 审计 manifest/evidence：`artifacts/reviewer-g2/manifest.json`、`evidence.sha256`。
- owner 交叉核对：`artifacts/m0-g2-broker/`（26/26）、`artifacts/m0-g2-integration/`（40/40）；报告/ADR hash 见 §0。
- 实时边界：LiveGate/gates/adapter/run_live 未改；容器 absence=0；rootfs/deps canonical。
