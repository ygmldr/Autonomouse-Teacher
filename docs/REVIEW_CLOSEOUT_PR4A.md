# PR4a 独立审计 — Mock Egress 边界与 billable-path inventory（无 Key）

- 版本：REVIEW-CLOSEOUT-PR4A-v1（2026-11-14 UTC）
- 审计者：`verify2`（非实现者；PR4a 由 `sdk-docs` 实现）
- 审计对象：冻结提交 **`8cf24766dd062f3b7038885de1c4f24eebd00559`**（PR4a，父 `7d2cd3e`）与 owner 证据
  **`artifacts/m0-egress-validation/manifest.json`**（sha256 `b04afbc945815936bc052e233e3ea622105cdda4940159f291c6760c75258082`；
  evidence `fff79077…`，19/19）。
- 原始证据：[`artifacts/reviewer-closeout-pr4a/`](../artifacts/reviewer-closeout-pr4a/)

## 0. 结论

**PASS_FOR_DECLARED_NO_KEY_PR4A_SCOPE_WITH_EGRESS_LIMITATION**：PR4a 冻结提交的 egress allowlist/deny 矩阵、失败矩阵、stable call-id、mock transport 与 billable-path inventory 在其声明范围内成立；**LIMITATION（锁定 OCI 内 `socket()` 即 PermissionError，无法做真实 HTTP mock/provider wire 观测）经独立复现为真；未把描述符级观测写成真实 wire/硬预算 PASS；Live 保持 BLOCKED**。

发现（均非安全功能阻断，需 owner errata/记录）：
- **V-PR4A-1（中低，证据准确性）**：owner manifest `baseline.head` 记录为 `9b77a37f0e9b8b0d1a8c7d8f0b5e0e1a2b3c4d5e0f61728394a5b6c7d8e9f0a`——这不是真实 commit（真实为 `9b77a3786c72a0f509f4c21d34f27314a92f3563`），系占位/伪造样式的错误 SHA；`baseline.pr1`（fdcfdc9）正确。建议 errata 更正为真实父提交。
- **V-PR4A-2（低，lint；post-freeze 已修）**：PR4a 冻结 commit 的 PR4a 路径 Ruff 有 7 个错误（`verify_egress_policy.py` F401 `sys`/F841 `transport`；`security/__init__.py` F401/F811/F401；`egress.py` F401 `json`/`Sequence`）。post-freeze commit `87f44e1` 已删除这些未用 import/变量；冻结提交本身 lint 红，不得声称 repo-wide Ruff PASS；无需功能重测。
- **O-PR4A-1（信息）**：evidence 中 3 个 repo 文件路径以工作树绑定；post-freeze 87f44e1 修改后当前工作树 `sha256sum -c` 为 16/19，**对冻结 commit 8cf2476 blob 为 19/19**（非篡改，建议 manifest 绑定 commit/blob）。

## 1. Git / 范围

| 项 | 结果 |
|---|---|
| commit | `8cf2476`，父 `7d2cd3e`，`2026-11-14 15:28:00Z` |
| 文件 | **6 个**：`docs/BILLABLE_PATH_INVENTORY.md`、`src/autoteacher_m0/security/egress.py`、`security/__init__.py`（导出）、`scripts/verify_egress_policy.py/.sh`、`tests/integration/sandbox/test_egress_boundary.py` |
| 混入 | 无 accounting/REVIEW/errata/artifacts 文件；`git diff --check` exit0；后续 PR4b commit `c802a32` **不改** PR4a 路径 |
| 文件 hash | 6/6 与 owner manifest 一致 |
| 历史证据 | phase5 `391767d3…`、PR2 `c6ea4e86…`、PR3 `b5c16f81…` 未改 |

## 2. 独立重跑（固定 digest 无 Key OCI；新 argv/UTC/exit/日志）

| 用例 | 结果 |
|---|---|
| `pytest tests/integration/sandbox/test_egress_boundary.py` | **24 passed**，exit0 |
| `scripts/verify_egress_policy.py` | **PASS，49 checks，failures=[]**，exit0 |
| 锁定 OCI socket 探针（`python -c "import socket; socket.socket()"`） | **PermissionError [Errno 13]**，exit1 → LIMITATION 为真 |
| Ruff（PR4a 路径） | **7 errors（冻结 commit）** → V-PR4A-2；post-freeze 87f44e1 已移除相关未用 import/变量 |
| Ruff（repo-wide） | 13 errors（7 PR4a + 4 PR1 + 2 其他历史），说明 repo-wide lint 仍红；PR4a 自身 7 个已由 87f44e1 修正 |
| 容器 absence | prefix `at-m0-rev-pr4a*` = 0；全局 `podman ps -a` = 0 |

## 3. 语义核验（源码 + 测试）

- **deny 矩阵在 dispatch 前**：`authorize()`（`egress.py:126-172`）依次检查 `NO_RESERVATION`、`ROUTE_MODEL_NOT_APPROVED`、`HOST_PORT_NOT_ALLOWED`、`METHOD_NOT_ALLOWED`、`PATH_NOT_ALLOWED`、`MAX_TOKENS_INVALID/EXCEEDED`、`FILES/IMAGES/STORE_NOT_PERMITTED`、`ATTEMPT_ORDINAL/ATTEMPT_LIMIT_EXCEEDED`；任何 reason 都返回 `allowed=False`，`require()` 抛 `EgressViolation`（`:211-217`）；测试 `test_unapproved_requests_denied_before_dispatch` 逐项断言。
- **失败矩阵**：`record_outcome()`（`:174-198`）；timeout/hang/disconnect/unknown_transport/5xx/无 usage/部分 usage → `BILLABLE_UNKNOWN` 且 `worst_case_held_usd > 0`；401/429 → `NOT_BILLABLE_HTTP_ERROR`；`retry_attempted` 恒 False，不自动重试；verifier 49 checks + pytest 24 项覆盖，独立 PASS。
- **call_id/join**：`_call_id()`（`:103-108`）由 `logical_stream_id|reservation_id|attempt_ordinal|route|model|host|port|path` sha256 前缀 `eg-` 生成；同 attempt 稳定、跨 attempt 改变；`EgressDecision` 暴露 join 字段；**不写 accounting 状态**（`egress.py` 无 ledger/broker import，`accounting_files_modified=false` 与审计一致；reservation id 仅 placeholder 接口）。
- **LIMITATION**：模块 docstring/owner manifest 明确锁定 OCI 拒绝 socket、mock 结果合成、非真实 wire/账单；独立 socket 探针复现 PermissionError，未发现隐藏真实网络路径；Live/E1–E5 保持 BLOCKED。

## 4. 证据链

- owner manifest `b04afbc9…`；`evidence.sha256` hash `fff79077…`；**对冻结 commit 19/19**（manifest/logs/probe/image 均 OK）；owner stage 79 文件 normalized `87a86716…` 独立复算一致；image `62d3569e…`/id `56db1e2a…`。
- 无真实 Key（仅 `sk-FAKE-PR4A-LOCAL-ONLY` 等假值）/模型/HTTP；宿主未跑项目代码；容器 absence=0；rootfs `25491e45…`/deps `e07729d7…` 保持。
- 未 git add/commit；只写审计报告与 gitignored 证据。

## 5. 残余 UNVERIFIED（不夸大）

1. 真实 provider wire/retry/cache/Files 行为未观测（锁定 OCI 无 socket；mock 结果为合成数据）——**这是 CI/OCI 环境限制，不是“真实硬预算”证据**。
2. reservation/accounting 集成与硬预算由 PR4b 审计；egress 仅读取 reservation placeholder，不写账本。
3. 真实 merged Provider/工具/网络策略、真实人类授权/凭据/OS 边界仍 BLOCKED；LiveGate/E1–E5/Live 不变。

## 6. 证据索引

- `artifacts/reviewer-closeout-pr4a/manifest.json`、`manifest.sha256`、`evidence.sha256`；独立 stage（158 文件）+`stage.tar`；`logs/`（pytest/verify/socket/ruff）+`commands.jsonl`（argv/UTC/exit/sha）。
- owner 交叉核对：`artifacts/m0-egress-validation/`（manifest `b04afbc9…`、evidence 19/19、stage `87a86716…`）。
