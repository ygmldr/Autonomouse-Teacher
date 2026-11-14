# PR4b 独立审计 — ProviderObservation/Usage 映射与 call identity（无 Key）

- 版本：REVIEW-CLOSEOUT-PR4B-v1（2026-11-14 UTC）
- 审计者：`verify2`（非实现者；PR4b 由 `broker-docs` 实现）
- 审计对象：冻结提交 **`c802a3292888394d65466510d3ad07ff82be89cf`**（PR4b，父 `8cf2476`）与 owner 证据
  **`artifacts/m0-usage-mapping/manifest.json`**（sha256 `de1bdb0746b5641d337e5cf247c4b7cd9ebfdba792440813f76259793b6469c0`）。
- 原始证据：[`artifacts/reviewer-closeout-pr4b/`](../artifacts/reviewer-closeout-pr4b/)

## 0. 结论

**PASS_FOR_DECLARED_NO_KEY_PR4B_SCOPE_WITH_REAL_WIRE_UNVERIFIED**：PR4b 冻结提交的 `ProviderObservation` 严格模式、四类 completeness 映射、broker v1 可选 `call_id` 兼容、additive ledger 表、幂等/冲突语义与 fail-first/159 通过证据在其离线范围内成立；**真实 provider wire/usage/invoice 仍 UNVERIFIED，未声称账单已核对；Live/E1–E5 仍 BLOCKED/DECISION PENDING**。

## 1. Git / 范围

| 项 | 结果 |
|---|---|
| commit | `c802a32`，父 `8cf2476`，`2026-11-14 15:30:47Z` |
| 文件 | **7 个**：`docs/PROVIDER_USAGE_MAPPING.md`、`accounting/observation.py`（新）、`accounting/{ledger,broker,__init__}.py`（改）、`tests/unit/accounting/test_provider_observation.py`、`tests/integration/budget_bridge/test_observation_broker.py` |
| 混入 | 无 egress/REVIEW/errata/artifacts 文件；`git diff --check` exit0；PR1–PR4a 路径未被本提交改写（PR4b 后仅 87f44e1 post-freeze lint 修改 PR1/PR4a 文件，非 PR4b） |
| 文件 hash | 7/7 与 owner manifest 一致；96e? stage accounting/tests 与 commit 完全一致（6/6 SAME；docs 不在 owner run stage，属正常） |
| 历史证据 | phase5 `391767d3…`、PR4a `b04afbc9…`、PR3 `b5c16f81…` 未改 |

## 2. 独立重跑（固定 digest 无 Key OCI；新 argv/UTC/exit/日志）

| 用例 | 结果 |
|---|---|
| `pytest tests/unit/accounting tests/integration/budget_bridge`（独立 commit stage） | **159 passed**，exit0 |
| Ruff（PR4b 路径：observation/ledger/broker/__init__/两个新测试） | **All checks passed**，exit0 |
| Ruff（repo-wide） | 13 errors（PR1 4 + PR4a 7 + PR2 2 历史/post-freeze 前状态；**非 PR4b 文件**）→ 跨 PR 残余，已知 |
| fail-first 交叉核对 | owner `raw/py-old-failfirst.log`（hash `b83fee38…`）为 **2 collection errors**（ImportError ProviderObservation/CallIdentity，exit2）；`raw/py-new-all2.log`（`47da5bf8…`）为 **159 passed**，与独立重跑一致 |
| 迭代证据 | `raw/py-new-all.log` 首次实现 3 个失败（test-helper call_id），修复后 159；保留未删 |
| 容器 absence | prefix `at-m0-rev-pr4b*` = 0；全局 0 |

## 3. ProviderObservation/Usage 语义（源码 + 测试）

- **14 字段严格 dataclass**：`requested_route` + `observed_route/model_reported/provider_request_id/usage_raw_hash/input/cache_read/cache_write/output/reasoning/cost_estimate/cost_source/error_kind/complete_or_uncertain`（`observation.py:95-130`）；字段类型/长度/哈希/非负计数/finite cost 校验；`COST_SOURCES`/`ERROR_KINDS`/`COMPLETENESS` 枚举；未知 schema/字段拒收（`from_mapping` `:176-197`，测试 `test_observation_schema_rejects_invalid_fields`/`test_unknown_or_missing_schema_keys_are_rejected`）；缺失保持 `None`，**从不填 0**。
- **四类状态映射**（`:199-240`）：`AUTHORITATIVE → SETTLED`（要求 error_kind=none、input/output 存在、input_total=cache_read+cache_write+input、reasoning 按显式 policy）；`PARTIAL/MISSING → WORST_CASE_HELD`（reservation 上界、无 cache 折扣、estimated、full fail、绝不 0）；`UNKNOWN → SETTLEMENT_UNCERTAIN`（PENDING 不释放/不退款/不重试）；`actual_cost_usd` 仅当 `cost_source=="provider_invoice"`，否则 None（本地估算不冒充账单）。
- **call identity**（`:248-277`）：`call-`+sha256(canonical {v,run_id,logical_step,attempt_index,request_digest})[0:48]，长度 53≤broker 96；测试覆盖 stability/bounded/injective；`derive_call_id` 供可信 Controller/PR4a 使用。
- **持久幂等交付**（`:279-324`）：`deliver_observation` 通过 `ledger.observation_once` 同一事务；同 call_id 同 payload 幂等（ALREADY_SETTLED），异 payload → 冲突；`UNKNOWN_CALL`/`UNKNOWN_RESERVATION` 返回 SETTLEMENT_UNCERTAIN+pending；UNKNOWN 不 settle/不退款。
- **broker v1**：`call_id` 为 `reserve` 的**可选**字段（`broker.py` diff `_keys(..., {"call_id"})`）；旧客户端不发送时行为完全不变；新增 `budget_call_links`/`budget_provider_observations` additive 表，不修改既有 reserve/settle/journal 语义（`ledger.py:127-183`）；`CALL_ID_CONFLICT` 在 journal 事务内 raise 回滚；旧 fixture/PR1 F2 测试仍通过（159 包含 148 旧 + 28 新）。
- **无 SDK 类型**：`observation.py` 不 import `deepseek_harness`/SDK；输入是普通 mapping；无真实 Key/网络。

## 4. 证据链与边界

- owner manifest `de1bdb07…`；`artifact-hashes.sha256` hash `79e816de…`，**8/8 OK**（raw 日志/result/git-state/absence 均校验）；fail-first exit2 + 159 passed 与日志一致；manifest `stages` old/new 由 7d2cd3e/PR4b worktree构建，accounting 文件与 final commit c802a32 逐字节一致；owner stage-pr4b 156 文件。
- 无真实 Key/模型/HTTP（0 calls；测试使用 synthetic/mock 映射）；宿主未跑项目代码；容器 absence=0；rootfs `25491e45…`/deps `e07729d7…`。
- **真实 wire/usage/invoice UNVERIFIED**：本 PR 只有 synthetic observation/映射与 broker 账本测试，没有真实 provider wire/账单；不得声称“真实 usage/账单已核对”或硬预算已证明（PR4a LIMITATION 同样存在）。
- E1–E5/LiveGate/Live 状态不变：BLOCKED/DECISION PENDING。

## 5. 观察/残余

- **O-PR4B-1（信息）**：owner 使用 `artifact-hashes.sha256`（8 项 raw 文件）而非任务描述的 `evidence.sha256` 命名；校验 8/8 OK，但 stage 目录/部分交付未纳入该 checksum。建议后续 manifest 统一 evidence/checksum 范围与命名。
- **O-PR4B-2（信息）**：owner 运行输入来自 run_base_head `7d2cd3e` + PR4b worktree，而冻结 commit `c802a32` 父为 `8cf2476`；已独立核对 accounting/tests 与 final commit 逐字节一致，且 PR4a 后 accounting 未变，故证据有效。
- **V-PR4B-1（低，可延后）**：repo-wide Ruff 在 PR4b 分支历史（c802a32）仍有 13 errors（全部来自 PR1/PR4a/PR2 文件，非 PR4b）；PR4b 自身 scoped clean；post-freeze 87f44e1 只修部分，需后续统一 lint 收口（不阻断 PR4b 功能/账本结论）。
- 真实 wire/usage/invoice/人类授权/OS 边界仍 UNVERIFIED；PR4b 仅离线映射与账本语义。

## 6. 证据索引

- `artifacts/reviewer-closeout-pr4b/manifest.json`、`manifest.sha256`、`evidence.sha256`；独立 commit stage（162 文件）+`stage.tar`；`logs/`（pytest/ruff）+`commands.jsonl`（argv/UTC/exit/sha）。
- owner 交叉核对：`artifacts/m0-usage-mapping/`（manifest `de1bdb07…`、artifact-hashes 8/8、raw fail-first/159 日志）。
