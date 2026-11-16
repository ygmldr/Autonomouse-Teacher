# M0 G2-L1.1 Errata — RED evidence correction

- 日期：2026-11-16 UTC；父 docs commit：`c140541cb2e0267cf3ba61703f7550a0f517b8b3`
- 性质：**证据/文档勘误，不改 `bf1e84d` 代码或测试，不 amend 历史**。
- 影响：仅 Review Packet 的 RED 证据；GREEN（`bf1e84d`）与 T1–T5 实现/测试结论不变。

## 1. 问题

Review Packet 的 `logs/red.stdout.log` 实际使用**旧测试版本**，不是在“精确基线 `76f1c52` + 当前已提交测试（`bf1e84d`）”上生成：

- `att_02/att_04/att_05` 报 `NameError: AttemptState`（当前提交测试顶部已 import）。
- `att_01` 报 `KeyError: 'classification'`（旧实现无新 API 字段；属 API-shape，不是目标行为 RED）。
- `diag_01` 报 `ROUTE_MODEL_NOT_APPROVED`（旧测试使用默认 policy，当前测试已显式使用离线 route）。
- 其 argv 指向 `artifacts/g2l11/stage-old`（旧测试副本），不满足 Playbook §13.4 精确基线 RED/§14 可复验性。

## 2. 修正证据（red2）

新建 `artifacts/g2l11/stage-old2`：
- 内容：`git archive 76f1c52` + 从实现提交 `bf1e84d` 覆盖 `tests/integration/g2_closure/test_g2l1_fix.py`、`tests/integration/sandbox/test_egress_boundary.py`。
- `src/` 三处关键文件 SHA-256 = 基线 `76f1c52` 字节（egress `c8c6f942…`、call_identity `4d92badf…`、broker `5439fb49…`）。
- stage file count 198；normalized tar sha256 `865c3993c97c981bc464bfb377101ca587fc2259900894aca66a3e7005a79603`；测试文件 sha256 `0b2339fee72eb054269285bad4b8af4e93b4e65173d340d3df566f3e5331a58b` / `fe4a8f19…`。

固定无 Key OCI 重跑 L11 选择集（`-k l11_`，镜像 `62d3569e…`，deps `e07729d7…`，network none/read-only/uid65534/cap-drop ALL）：
- **真实结果：8 failed / 16 passed**，exit 1；日志 `artifacts/g2l11/logs/red2.stdout.log`、`red2-detail.log`；argv/UTC/exit `artifacts/g2l11/argv/red2.argv.json`。
- **行为 RED（6）**：`L11-ATT-03`（provider_calls 1!=0/未进入归因）、`L11-ATT-04`（NOT_DISPATCHED != BILLABLE_UNKNOWN）、`L11-ATT-06`（KeyboardInterrupt 未抛出）、`L11-ID-02`（Unicode call-id 两侧不一致）、`L11-JRN-01`（未知 completion 产生 6 条 journal 行，期望 0）、`L11-DIAG-01`（诊断消耗 attempt 配额，ATTEMPT_LIMIT_EXCEEDED）。
- **API-shape RED（2，不冒充行为 RED）**：`L11-ATT-01`（旧实现无 `classification` 字段，`KeyError`）、`L11-DIAG-02`（旧实现无 `policy_checks` 属性，`AttributeError`）。
- **red2 中 16 passed**：含 `L11-PREP-01/02`。注：旧实现可能因 digest 不一致先行拒绝，故这两项在旧基线通过并不能单独证明 schema 检查存在；GREEN 的新测试仍断言显式 schema/类型拒绝（已在 `bf1e84d` 中通过）。此注不改变 GREEN 结果，仅防止把旧基线 PASS 误读为 T3 已修复。

## 3. 对结论的影响

- T1/T2/T4/T5 的 RED 已按精确基线重跑；T3 的 GREEN 断言仍由 `bf1e84d` L11-PREP-01..05 覆盖（旧基线 PREP-01/02 通过属 digest 先行拒绝的替代路径，不记为“T3 已修复”的行为 RED）。
- **不影响**：`bf1e84d` GREEN（L11 24 passed）、全量 625 passed/1 skipped、verify PASS、Ruff clean、T6 Python 回归结论。
- 仍 **BLOCKED/UNVERIFIED**：T6 DSH Plugin/SDK B 层（OCI 无 node，未运行）；真实 wire/usage/invoice/exactly-once 属 G3。

## 4. Packet 更新（旧 red 字节保留为历史）

- 旧 `logs/red.stdout.log` 等**字节未改**，保留并标记 superseded（`logs/red-old-superseded.txt`）。
- 新 RED 证据：`logs/red2.stdout.log`/`red2.stderr.log`/`red2.argv.json`/`red2-detail.log`；`logs/stage-old2-identity.txt`。
- 更新 README/CHANGELOG/manifest/evidence-matrix/hashes/integrity/reviewer-reproduction。
- 更新后 Packet：文件 49；`manifest.sha256`=`a4e1938521ffce0a0af4c91200f4c24e49fcd6bffae89689633209aec0ad904a`；`hashes.sha256`=`c7492979732a1ebf7f3244f1f4834dc368e0ba3b9c03f13997c34f4374927730`；packet tar=`96ca6959d643064896c1f93c2d683594fadaac671a98b221ae2aa1d3144b16b7`。
- Packet 的 base/impl/docs 绑定仍为 `76f1c52`/`bf1e84d`/`c140541`；本 errata 为后续 docs-only commit，不重写实现身份。

## 5. 状态

- 修复证据完整性；不改 Live 硬阻断、不进入 G3；等待 Lead 复核后派独立 Reviewer。
